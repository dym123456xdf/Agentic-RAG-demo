"""文档加载器 —— 单一职责:把文件 / 目录读成 llama-index Document 列表。

支持格式: .pdf / .md / .markdown / .docx / .pptx / .txt

两个绕坑:
1. .md 文件不走 UnstructuredReader —— 它会把 # 头部抹掉,导致 MarkdownNodeParser 退化成 1 个节点。
2. 目录要递归走 glob,UnstructuredReader 只吃单文件不吃目录。

MinerU 通道(MINERU_ENABLED=true):PDF/DOCX/PPTX 先经 mineru CLI 转成 Markdown,
落盘 converted/<原文件名>.md 供用户人工检查转换质量,入库内容即该 Markdown;
同名产物已存在时直接复用,不重复转换;转换失败快速抛错,不静默回退。
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from llama_index.core import Document

from app.core.config import Config

SUPPORTED = {".pdf", ".md", ".markdown", ".docx", ".pptx", ".txt"}
# MinerU 可转换的二进制文档类型;.md/.txt 本身就是可读文本,无需转换
MINERU_CONVERTIBLE = {".pdf", ".docx", ".pptx"}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def converted_md_path(path: Path) -> Path:
    """MinerU 转换产物的固定落盘位置:converted/<原文件名>.md(带原后缀防同名冲突)。"""
    return Config.MINERU_OUTDIR / f"{path.name}.md"


def convert_to_markdown(path: Path) -> Path:
    """PDF/DOCX/PPTX 经 mineru 转成 Markdown 并落盘,返回产物路径。

    - 产物已存在:直接复用(支持"检查过质量 → 重传快速入库")
    - 失败(非零退出 / 超时 / 无产物):抛 RuntimeError 含 stderr 摘要,不写坏文件
    """
    target = converted_md_path(path)
    if target.exists():
        return target

    Config.MINERU_OUTDIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mineru_") as td:
        out_dir = Path(td)
        try:
            proc = subprocess.run(
                [Config.MINERU_BIN, "-p", str(path), "-o", str(out_dir)],
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

        produced = sorted(out_dir.rglob("*.md"))
        if not produced:
            raise RuntimeError(
                f"MinerU 未产出 Markdown: {path.name}\n"
                f"stderr 摘要: {(proc.stderr or '')[-500:]}"
            )
        target.write_text(produced[0].read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
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
        # MinerU 通道:转 Markdown 落盘 converted/ 再读,用户可先检查转换质量
        md_path = convert_to_markdown(path)
        return [Document(text=_read_text(md_path), metadata=meta_base)]

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
