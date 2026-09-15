"""文档切分器 —— 单一职责:把 Document 列表切成 Node 列表。

按 Markdown 标题层级切,保证每个片段语义完整。
非 markdown 文档(纯文本)没有标题,就退化成整篇当一个 Node,这种情况 PDF/DOCX/PPTX 经 UnstructuredReader
出来的内容通常也已经按段落分开,影响可控。
"""
from __future__ import annotations

from typing import List

from llama_index.core import Document
from llama_index.core.node_parser import MarkdownNodeParser


def split(docs: List[Document]) -> List:
    parser = MarkdownNodeParser()
    nodes = parser.get_nodes_from_documents(documents=docs, show_progress=False)
    print(f"[splitter] 切出 {len(nodes)} 个 Node")
    return nodes