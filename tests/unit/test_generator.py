"""答案生成器单元测试。"""
from __future__ import annotations

from typing import Any

import pytest
from llama_index.core.schema import NodeWithScore, TextNode

from app.rag.generator import Generator


def _make_node(text: str = "内容片段", score: float = 0.9, source: str = "doc.md") -> NodeWithScore:
    n = TextNode(text=text, metadata={"source": source, "doc_id": "abc123"})
    return NodeWithScore(node=n, score=score)


@pytest.fixture()
def generator(fake_llm) -> Generator:  # type: ignore[no-untyped-def]
    gen = Generator.__new__(Generator)
    gen._llm = fake_llm
    return gen


class TestGenerator:
    def test_no_nodes_returns_default(self, generator: Generator) -> None:
        result = generator.generate("query", [])
        assert result["answer"] == "我不知道,资料里没提到。"
        assert result["sources"] == []

    def test_with_nodes_returns_answer_and_sources(self, generator: Generator) -> None:
        nodes: list[Any] = [_make_node("关于 embedding 的内容")]
        result = generator.generate("什么是 embedding?", nodes)
        assert result["answer"]
        assert len(result["sources"]) == 1
        assert result["sources"][0]["source"] == "doc.md"
        assert result["sources"][0]["index"] == 1

    def test_sources_have_required_fields(self, generator: Generator) -> None:
        nodes = [_make_node("a"), _make_node("b")]
        result = generator.generate("q", nodes)
        for i, src in enumerate(result["sources"], 1):
            assert src["index"] == i
            assert "content" in src
            assert "score" in src
            assert "source" in src

    def test_llm_called_with_context(self, generator: Generator, fake_llm) -> None:  # type: ignore[no-untyped-def]
        nodes = [_make_node("Embedding 是向量表示")]
        generator.generate("什么是 embedding?", nodes)
        assert fake_llm.calls
        call = fake_llm.calls[-1]
        assert call["type"] == "chat"
        user_msg = call["messages"][-1]["content"]
        assert "Embedding 是向量表示" in user_msg
        assert "什么是 embedding?" in user_msg
