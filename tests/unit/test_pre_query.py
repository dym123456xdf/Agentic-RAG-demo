"""查询预处理器单元测试。"""
from __future__ import annotations

import pytest

from app.rag.pre_query import ProcessedQuery, QueryPreProcessor


@pytest.fixture()
def processor(fake_llm):  # type: ignore[no-untyped-def]
    return QueryPreProcessor(llm=fake_llm)


class TestProcessedQuery:
    def test_dataclass_defaults(self) -> None:
        pq = ProcessedQuery(original="test", rewritten="test")
        assert pq.expanded == []
        assert pq.intent == "factual"


class TestQueryPreProcessor:
    def test_process_returns_processed_query(self, processor: QueryPreProcessor) -> None:
        result = processor.process("什么是 embedding?", history=[])
        assert isinstance(result, ProcessedQuery)
        assert result.original == "什么是 embedding?"

    def test_no_history_skips_rewrite(self, processor: QueryPreProcessor, fake_llm) -> None:  # type: ignore[no-untyped-def]
        processor.process("什么是 embedding?", history=[])
        # 没有历史时不应调改写
        assert all("改写" not in c["prompt"] for c in fake_llm.calls)

    def test_with_history_calls_rewrite(self, processor: QueryPreProcessor, fake_llm) -> None:  # type: ignore[no-untyped-def]
        history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        processor.process("它是什么?", history=history)
        assert any("改写" in c["prompt"] for c in fake_llm.calls)

    def test_intent_recognised(self, processor: QueryPreProcessor) -> None:
        result = processor.process("什么是 embedding?", history=[])
        assert result.intent == "factual"

    def test_expanded_not_empty(self, processor: QueryPreProcessor) -> None:
        result = processor.process("什么是 embedding?", history=[])
        assert len(result.expanded) >= 1
