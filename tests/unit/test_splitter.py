"""文档切分器单元测试。"""
from __future__ import annotations

from llama_index.core import Document

from app.rag.splitter import split

MD = """# 标题一
第一段内容。

## 子标题
第二段内容。

## 另一个子标题
第三段内容。
"""


class TestSplitter:
    def test_markdown_splits_by_headers(self) -> None:
        docs = [Document(text=MD, metadata={"source": "test.md"})]
        nodes = split(docs)
        assert len(nodes) >= 2

    def test_nodes_carry_source_metadata(self) -> None:
        docs = [Document(text=MD, metadata={"source": "my_doc.md"})]
        nodes = split(docs)
        for n in nodes:
            assert n.metadata.get("source") == "my_doc.md"

    def test_empty_document_returns_empty(self) -> None:
        docs: list = []
        assert split(docs) == []

    def test_plain_text_single_node(self) -> None:
        docs = [Document(text="没有标题的纯文本内容", metadata={"source": "plain.txt"})]
        nodes = split(docs)
        assert len(nodes) == 1
