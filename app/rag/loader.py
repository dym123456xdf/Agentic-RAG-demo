"""文档加载器 —— 单一职责:把文件 / 目录读成 llama-index Document 列表。

支持格式: .pdf / .md / .markdown / .docx / .pptx / .txt

两个绕坑:
1. .md 文件不走 UnstructuredReader —— 它会把 # 头部抹掉,导致 MarkdownNodeParser 退化成 1 个节点。
2. 目录要递归走 glob,UnstructuredReader 只吃单文件不吃目录。

MinerU 通道(MINERU_ENABLED=true):PDF/DOCX/PPTX 先经 mineru CLI 转成 Markdown,
产物集中落盘 converted/<stem>/(md 与 images/ 同级,stem 为原文件名去后缀)供用户人工检查
转换质量;同名产物已存在时直接复用,不重复转换;转换失败快速抛错,不静默回退。
入库时图片相对路径会在内存里改写为 /converted/<stem>/images/x 绝对 URL,落盘文件不动。
"""
from __future__ import annotations

import base64
import hashlib
import re
import subprocess
import tempfile
from pathlib import Path

from llama_index.core import Document

from app.core.config import Config

SUPPORTED = {".pdf", ".md", ".markdown", ".docx", ".pptx", ".txt"}
# MinerU 可转换的二进制文档类型;.md/.txt 本身就是可读文本,无需转换
MINERU_CONVERTIBLE = {".pdf", ".docx", ".pptx"}

# 匹配 MinerU 输出里的 base64 内嵌图:`![](data:image/jpeg;base64,<...>)`
_BASE64_IMG_RE = re.compile(
    r"!\[[^\]]*\]\(data:image/(\w+);base64,([A-Za-z0-9+/=]+)\)"
)
# 匹配产物 md 里的相对图片引用:`![alt](images/xxx.jpeg)`
_REL_IMG_RE = re.compile(r"!\[([^\]]*)\]\(images/([^)/\s]+)\)")
_IMAGES_SUBDIR = "images"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def converted_md_path(path: Path) -> Path:
    """MinerU 转换产物的固定落盘位置:converted/<stem>/<stem>.md(stem 为原文件名去后缀)。"""
    return Config.MINERU_OUTDIR / path.stem / f"{path.stem}.md"


def _rewrite_image_urls(md: str, stem: str) -> str:
    """入库文本专用:把 `![alt](images/x)` 改写为 `![alt](/converted/<stem>/images/x)` 绝对 URL。

    只改内存里的文本,落盘 md 保持相对路径(人工核对与管理页弹层渲染依赖相对形态)。
    用 lambda 替换避免 stem 里出现反斜杠时被当作 re 替换转义。
    """
    return _REL_IMG_RE.sub(
        lambda m: f"![{m.group(1)}](/converted/{stem}/images/{m.group(2)})", md
    )


def _extract_base64_images(md: str, images_dir: Path) -> str:
    """把 md 文本里 base64 内嵌图抽到 images_dir,文本里替换为 images/<hash>.<ext>。

    返回改写后的 md 文本。base64 解码失败/重复图片:跳过不抛错(尽力而为)。
    """
    def _repl(m: re.Match) -> str:
        ext = m.group(1).lower()
        try:
            data = base64.b64decode(m.group(2))
        except Exception:
            return m.group(0)  # 解码失败保留原文
        digest = hashlib.sha1(data).hexdigest()[:8]
        out_path = images_dir / f"{digest}.{ext}"
        if not out_path.exists():
            out_path.write_bytes(data)
        return f"![image](images/{digest}.{ext})"

    return _BASE64_IMG_RE.sub(_repl, md)


def convert_to_markdown(path: Path) -> Path:
    """PDF/DOCX/PPTX 经 mineru-kit 转成 Markdown 并落盘,返回产物路径。

    - 产物已存在:直接复用(支持"检查过质量 → 重传快速入库")
    - 失败(非零退出 / 超时 / 无 md):抛 RuntimeError 含 stderr 摘要
    - 抽 base64 内嵌图到 MINERU_OUTDIR/<stem>/images/,md 文本 base64 引用替换为相对路径
    - md 落盘 MINERU_OUTDIR/<stem>/<stem>.md(与 images/ 同级,保留 converted_md_path() 契约)

    CLI 选型:`mineru-kit parse <path> --tier basic -o <dir> -f markdown`。
    与 `mineru parse`(顶层 CLI)共用同一 backend,但:
    - `mineru parse`:stdout markdown 文本流,图片是 `![Image block](doc:...)` 占位符
    - `mineru-kit parse -o <dir>`:产物写到目录,图片以 base64 内嵌进 md,真实可显示
    """
    target = converted_md_path(path)
    if target.exists():
        return target

    Config.MINERU_OUTDIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mineru_") as td:
        try:
            proc = subprocess.run(
                [
                    Config.MINERU_KIT_BIN,
                    "parse",
                    str(path),
                    "--tier", "basic",
                    "-o", str(td),
                    "-f", "markdown",
                ],
                capture_output=True,
                text=True,
                timeout=Config.MINERU_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"MinerU 转换超时(上限 {Config.MINERU_TIMEOUT_S}s): {path.name}"
            ) from exc

        if proc.returncode != 0:
            raise RuntimeError(
                f"MinerU 转换失败(returncode={proc.returncode}): {path.name}\n"
                f"stderr 摘要: {(proc.stderr or '')[-500:]}"
            )

        produced = sorted(Path(td).glob("*.md"))
        if not produced:
            raise RuntimeError(
                f"MinerU 未产出 Markdown: {path.name}\n"
                f"stderr 摘要: {(proc.stderr or '')[-500:]}"
            )
        raw_md = produced[0].read_text(encoding="utf-8", errors="ignore")

    # 后处理:base64 内嵌图 → 真实落盘 + md 文本相对路径化
    images_dir = Config.MINERU_OUTDIR / path.stem / _IMAGES_SUBDIR
    images_dir.mkdir(parents=True, exist_ok=True)
    rewritten = _extract_base64_images(raw_md, images_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rewritten, encoding="utf-8")
    return target


def _load_one(path: Path) -> list[Document]:
    """根据后缀选择加载器,返回 Document 列表(可能多个,看 PDF 页数)。"""
    suffix = path.suffix.lower()
    if suffix not in Config.ALLOWED_EXTS:
        return []

    meta_base = {"source": path.name}

    if suffix in {".md", ".markdown", ".txt"}:
        # markdown 文本直读,保留 # 标题,后面 MarkdownNodeParser 才有结构可切
        return [Document(text=_read_text(path), metadata=meta_base)]

    if Config.MINERU_ENABLED:
        # MinerU 通道:转 Markdown 落盘 converted/<stem>/ 再读,用户可先检查转换质量;
        # 入库文本里图片相对路径改写为绝对 URL,检索回来前端可直接渲染(落盘文件不动)
        md_path = convert_to_markdown(path)
        text = _rewrite_image_urls(_read_text(md_path), path.stem)
        return [Document(text=text, metadata=meta_base)]

    # UnstructuredReader 兜底(MinerU 关闭时,行为与历史版本一致)
    from llama_index.readers.file import UnstructuredReader

    # 其它格式走 UnstructuredReader
    from llama_index.readers.file.unstructured import UnstructuredReader as UR2  # noqa: F401

    reader = UnstructuredReader()
    docs = reader.load_data(file=path, split_documents=False)
    # 强制补 metadata(不同格式下 reader 行为不一致)
    for d in docs:
        d.metadata = {**d.metadata, **meta_base}
    return docs


def load(path: str | Path) -> list[Document]:
    """入口:接受文件或目录。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"路径不存在: {p}")

    if p.is_file():
        docs = _load_one(p)
    else:
        # 目录:递归 glob 所有支持的格式
        docs = []
        for ext in Config.ALLOWED_EXTS:
            for f in p.rglob(f"*{ext}"):
                docs.extend(_load_one(f))

    if not docs:
        raise RuntimeError(f"未在 {p} 找到任何支持的文档(支持: {sorted(Config.ALLOWED_EXTS)})")

    print(f"[loader] 加载了 {len(docs)} 个 Document(来自 {p})")
    return docs
