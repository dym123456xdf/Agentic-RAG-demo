"""文档加载器 —— 单一职责:把文件 / 目录读成 llama-index Document 列表。

支持格式: .pdf / .md / .markdown / .docx / .pptx / .txt

两个绕坑:
1. .md 文件不走 UnstructuredReader —— 它会把 # 头部抹掉,导致 MarkdownNodeParser 退化成 1 个节点。
2. 目录要递归走 glob,UnstructuredReader 只吃单文件不吃目录。
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Union

from llama_index.core import Document

from app.core.config import Config


SUPPORTED = {".pdf", ".md", ".markdown", ".docx", ".pptx", ".txt"}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _load_one(path: Path) -> List[Document]:
    """根据后缀选择加载器,返回 Document 列表(可能多个,看 PDF 页数)。"""
    suffix = path.suffix.lower()
    if suffix not in Config.ALLOWED_EXTS:
        return []

    meta_base = {"source": path.name}

    if suffix in {".md", ".markdown", ".txt"}:
        # markdown 文本直读,保留 # 标题,后面 MarkdownNodeParser 才有结构可切
        return [Document(text=_read_text(path), metadata=meta_base)]

    # 其它格式走 UnstructuredReader
    from llama_index.readers.file import UnstructuredReader
    from llama_index.readers.file.unstructured import UnstructuredReader as UR2  # noqa: F401

    reader = UnstructuredReader()
    docs = reader.load_data(file=str(path), split_documents=False)
    # 强制补 metadata(不同格式下 reader 行为不一致)
    for d in docs:
        d.metadata = {**d.metadata, **meta_base}
    return docs


def load(path: Union[str, Path]) -> List[Document]:
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