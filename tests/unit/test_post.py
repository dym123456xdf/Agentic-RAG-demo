"""后处理器单元测试。"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from llama_index.core.schema import NodeWithScore, TextNode

from app.rag.post import PostProcessor


def _make_node(text: str = "chunk", score: float = 0.5) -> NodeWithScore:
    return NodeWithScore(node=TextNode(text=text), score=score)


@pytest.fixture()
def processor() -> PostProcessor:
    return PostProcessor()


class TestPostProcessor:
    def test_empty_input_returns_empty(self, processor: PostProcessor) -> None:
        result = processor.process([], "query")
        assert result == []

    def test_cutoff_filters_high_distance(self, processor: PostProcessor) -> None:
        nodes = [_make_node(score=0.1), _make_node(score=10.0)]  # 10.0 > 默认 cutoff 2.0
        with patch("app.rag.post._get_reranker") as mock_reranker:
            mock_reranker.return_value.predict.return_value = [0.9, 0.1]
            result = processor.process(nodes, "query")
        assert len(result) == 1
        assert result[0].score == 0.9

    def test_none_score_nodes_filtered(self, processor: PostProcessor) -> None:
        node = NodeWithScore(node=TextNode(text="x"), score=None)
        result = processor.process([node], "q")
        assert result == []

    def test_reranker_called_with_pairs(self, processor: PostProcessor) -> None:
        nodes = [_make_node("hello", score=0.1), _make_node("world", score=0.2)]
        with patch("app.rag.post._get_reranker") as mock_reranker:
            mock_reranker.return_value.predict.return_value = [0.8, 0.9]
            processor.process(nodes, "my query")
            call_args = mock_reranker.return_value.predict.call_args
            pairs = call_args[0][0]
            assert pairs == [("my query", "hello"), ("my query", "world")]

    def test_top_n_limits_results(self, processor: PostProcessor) -> None:
        nodes = [_make_node(score=0.1) for _ in range(20)]
        with patch("app.rag.post._get_reranker") as mock_reranker:
            mock_reranker.return_value.predict.return_value = [0.5] * 20
            result = processor.process(nodes, "q")
        assert len(result) <= processor._top_n
