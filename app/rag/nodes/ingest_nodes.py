"""入库图 7 节点 —— 入口 → PDF转MD → 图片处理 → 切分 → 商品识别 → BGE嵌入 → 入Milvus。

依赖模块:
- 入口/转换/产物上传用 MinIO 客户端
- 嵌入用 BGE-M3
- 写入用 milvus_hybrid
"""
from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from llama_index.core import Document
from llama_index.core.node_parser import MarkdownNodeParser

from app.core import bge_embedding, minio_client
from app.core.config import Config
from app.core.milvus_hybrid import insert_chunks
from app.rag.base import BaseNode, IngestProcessError
from app.rag.state import ImportGraphState

# 与旧 loader.py 保持一致的常量
_BASE64_IMG_RE = re.compile(
    r"!\[[^\]]*\]\(data:image/(\w+);base64,([A-Za-z0-9+/=]+)\)"
)
_REL_IMG_RE = re.compile(r"!\[([^\]]*)\]\(images/([^)/\s]+)\)")


# ========== NodeEntry ==========

class NodeEntry(BaseNode[ImportGraphState]):
    """入口节点:把 task_id、import_file_path(MinIO key)、file_title(stem)写入 state。

    期望由 ingest() 入口调用时传入 task_id 与 minio_key(file_path),
    该节点不做实际 IO,仅填充元数据。
    """
    name = "entry"
    flow = "ingest"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        # 关键字段缺失直接报错,避免下游节点拿空字符串做无意义 IO
        if not state.get("import_file_path"):
            raise IngestProcessError("import_file_path 缺失", self.name)
        if not state.get("task_id"):
            raise IngestProcessError("task_id 缺失", self.name)
        # stem = 原文件名去后缀
        fname = Path(state["import_file_path"]).name
        state["file_title"] = Path(fname).stem
        state["file_dir"] = f"converted/{state['file_title']}"
        state["pdf_path"] = state["import_file_path"]
        return state


# ========== NodePdfToMd ==========

class NodePdfToMd(BaseNode[ImportGraphState]):
    """MinerU 转换:从 MinIO 拉原文件 → 子进程 mineru-kit → staging 落 md + images/。

    分支:
    - 扩展名 ∈ {pdf, docx, pptx} → 走 MinerU
    - 扩展名 ∈ {md, markdown, txt} → 直接读文件作为 md_content(不需要 MinerU)
    - 转换产物路径:`MINERU_OUTDIR/<stem>/<stem>.md` + `images/` 同级(无 /auto/ 段)。
    - 产物已存在则跳过转换,直接复用(同名文件重传时的快速路径)。
    """
    name = "pdf_to_md"
    flow = "ingest"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        import_file_path = state["import_file_path"]
        file_title = state["file_title"]
        ext = Path(import_file_path).suffix.lower()

        # .md / .markdown / .txt 不走 MinerU,直接读文件
        if ext in (".md", ".markdown", ".txt"):
            md_content = _read_text_from_minio(import_file_path)
            state["md_content"] = md_content
            state["md_path"] = "(direct read, no staging)"
            return state

        # PDF/DOCX/PPTX 走 MinerU
        from app.rag.loader_compat import MINERU_CONVERTIBLE
        if ext not in MINERU_CONVERTIBLE:
            raise IngestProcessError(f"不支持的文件类型: {ext}({file_title})", self.name)
        if not Config.MINERU_ENABLED:
            raise IngestProcessError("MINERU_ENABLED=false 时无法转换 PDF/DOCX/PPTX", self.name)

        # 目标 staging 路径(与原 loader.py 一致,无 /auto/ 段)
        staging_md = Config.MINERU_OUTDIR / file_title / f"{file_title}.md"
        staging_dir = Config.MINERU_OUTDIR / file_title
        staging_md.parent.mkdir(parents=True, exist_ok=True)

        # 产物已存在直接复用
        if staging_md.exists():
            state["md_content"] = staging_md.read_text(encoding="utf-8", errors="ignore")
            state["md_path"] = str(staging_md)
            return state

        # 从 MinIO 下载到本地临时文件供 mineru-kit 子进程读取
        with tempfile.TemporaryDirectory(prefix="mineru_") as td:
            local_in = Path(td) / Path(import_file_path).name
            _download_from_minio(import_file_path, local_in)

            try:
                proc = subprocess.run(
                    [
                        Config.MINERU_KIT_BIN,
                        "parse",
                        str(local_in),
                        "--tier", "basic",
                        "-o", str(td),
                        "-f", "markdown",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=Config.MINERU_TIMEOUT_S,
                )
            except subprocess.TimeoutExpired as exc:
                raise IngestProcessError(
                    f"MinerU 转换超时({Config.MINERU_TIMEOUT_S}s): {file_title}", self.name
                ) from exc

            if proc.returncode != 0:
                raise IngestProcessError(
                    f"MinerU 失败(rc={proc.returncode}): {file_title}\nstderr 摘要: {(proc.stderr or '')[-500:]}",
                    self.name,
                )

            produced = sorted(Path(td).glob("*.md"))
            if not produced:
                raise IngestProcessError(
                    f"MinerU 未产出 md: {file_title}\nstderr 摘要: {(proc.stderr or '')[-500:]}",
                    self.name,
                )
            raw_md = produced[0].read_text(encoding="utf-8", errors="ignore")

        # 后处理:base64 内嵌图 → images/ 真实落盘 + md 文本相对路径化
        images_dir = staging_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        md_content = _extract_base64_images(raw_md, images_dir)
        staging_md.write_text(md_content, encoding="utf-8")

        state["md_content"] = md_content
        state["md_path"] = str(staging_md)
        return state


def _read_text_from_minio(minio_key: str) -> str:
    """从 MinIO 读文本对象(用于 .md/.txt 直读路径),返回 utf-8 文本。"""
    buf = io.BytesIO()
    for chunk in minio_client.get_object_stream(minio_key):
        buf.write(chunk)
    return buf.getvalue().decode("utf-8", errors="ignore")


def _download_from_minio(minio_key: str, local_path: Path) -> None:
    """从 MinIO 流式拉到本地文件。"""
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with local_path.open("wb") as out:
        for chunk in minio_client.get_object_stream(minio_key):
            out.write(chunk)


def _extract_base64_images(md: str, images_dir: Path) -> str:
    """把 md 文本里 base64 内嵌图抽到 images_dir,文本里替换为 images/<hash>.<ext>。"""

    def _repl(m: re.Match) -> str:
        import base64
        import hashlib

        ext = m.group(1).lower()
        try:
            data = base64.b64decode(m.group(2))
        except Exception:
            return m.group(0)
        digest = hashlib.sha1(data).hexdigest()[:8]
        out_path = images_dir / f"{digest}.{ext}"
        if not out_path.exists():
            out_path.write_bytes(data)
        return f"![image](images/{digest}.{ext})"

    return _BASE64_IMG_RE.sub(_repl, md)


# ========== NodeMdImg ==========

class NodeMdImg(BaseNode[ImportGraphState]):
    """图片引用规范化:`![alt](images/x)` 改写为 `![alt](/converted/<stem>/images/x)` 绝对 URL。

    只改内存文本(staging md 文件保持相对路径,人工核对与管理页弹层依赖相对形态)。
    """
    name = "md_img"
    flow = "ingest"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        md = state.get("md_content", "")
        stem = state["file_title"]
        rewritten = _REL_IMG_RE.sub(
            lambda m: f"![{m.group(1)}](/converted/{stem}/images/{m.group(2)})", md
        )
        state["md_content"] = rewritten
        return state


# ========== NodeDocSplit ==========

class NodeDocSplit(BaseNode[ImportGraphState]):
    """MarkdownNodeParser 切分 → chunks: [{text, metadata, doc_id, chunk_idx}]。

    metadata 仅保留 source(原文件名)与 doc_id(stem + 前 50 字符 hash),其余 header_path 等丢。
    """
    name = "doc_split"
    flow = "ingest"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        import hashlib

        md = state["md_content"]
        stem = state["file_title"]
        doc = Document(text=md, metadata={"source": Path(state["import_file_path"]).name})
        parser = MarkdownNodeParser()
        nodes = parser.get_nodes_from_documents(documents=[doc], show_progress=False)

        chunks: list[dict] = []
        for idx, n in enumerate(nodes):
            text = n.get_content()
            doc_id = hashlib.md5(f"{stem}|{text[:50]}".encode()).hexdigest()[:16]
            chunks.append({
                "text": text,
                "metadata": {
                    "source": doc.metadata["source"],
                    "doc_id": doc_id,
                },
                "doc_id": doc_id,
                "chunk_idx": idx,
            })
        state["chunks"] = chunks
        return state


# ========== NodeItemNameRecognition ==========

class NodeItemNameRecognition(BaseNode[ImportGraphState]):
    """可选节点:LLM 抽商品/主题名(item_name),仅供程序员调试用,不参与检索。"""
    name = "item_name_recognition"
    flow = "ingest"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        from app.core.llm import LLMClient

        chunks = state.get("chunks") or []
        if not chunks:
            return state
        # 取前 3 个 chunk,各 2500 字符,拼 prompt 让 LLM 抽核心名词
        sample = "\n\n".join(c["text"][:2500] for c in chunks[:3])
        llm = LLMClient(role="fast")
        prompt = (
            "你是知识库整理助手。下面是一份文档的前几个片段,"
            "请输出该文档的核心商品名 / 主题名(只输出名词本身,不要解释,不要标点):\n\n"
            f"{sample[:6000]}"
        )
        try:
            name = llm.complete(prompt, temperature=0.0, max_tokens=40).strip()
            state["item_name"] = name.strip("「」[]\"'")[:100]
        except Exception:
            # 抽不到不影响入库
            state["item_name"] = ""
        return state


# ========== NodeBgeEmbedding ==========

class NodeBgeEmbedding(BaseNode[ImportGraphState]):
    """BGE-M3 双向量:每个 chunk 加 dense(1024)+ sparse(CSR dict)。

    任一向量为空的 chunk 在 import_milvus 节点里会被跳过。
    """
    name = "bge_embedding"
    flow = "ingest"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        chunks = state.get("chunks") or []
        if not chunks:
            return state
        texts = [c["text"] for c in chunks]
        # dense 批 + sparse 批
        dense_vecs = bge_embedding._encode_dense(texts)
        sparse_vecs = bge_embedding.encode_sparse_batch(texts)
        for c, d, s in zip(chunks, dense_vecs, sparse_vecs, strict=False):
            c["dense"] = d
            c["sparse"] = s
            c["doc_name"] = Path(state["import_file_path"]).name
            c["file_dir"] = state["file_dir"]
        state["chunks"] = chunks
        return state


# ========== NodeImportMilvus ==========

class NodeImportMilvus(BaseNode[ImportGraphState]):
    """入库收尾:写 Milvus + staging 整目录上传 MinIO + 本地 staging 删除。"""
    name = "import_milvus"
    flow = "ingest"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        chunks = state.get("chunks") or []
        # 1. Milvus 写入
        n_written = insert_chunks(chunks)

        # 2. staging 整目录上传 MinIO(file_dir 前缀,与 URL 契约一致,无 /auto/ 段)
        staging_dir = Config.MINERU_OUTDIR / state["file_title"]
        n_uploaded = 0
        if staging_dir.is_dir():
            try:
                n_uploaded = minio_client.upload_directory(
                    str(staging_dir), state["file_dir"]
                )
            except Exception as e:
                raise IngestProcessError(
                    f"staging 上传 MinIO 失败: {e}", self.name
                ) from e

            # 3. 删除本地 staging(转换完成即清)
            shutil.rmtree(staging_dir, ignore_errors=True)
            # 顺手清理 parent stem 目录(若为空)
            stem_dir = Config.MINERU_OUTDIR / state["file_title"]
            if stem_dir.is_dir() and not any(stem_dir.iterdir()):
                stem_dir.rmdir()

        state["chunks_ingested"] = n_written
        state["uploaded_objects"] = n_uploaded
        return state
