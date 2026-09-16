"""测试配置 —— 单一职责:提供可复用的 fixtures,mock 掉所有外部依赖(LLM / Milvus / Embedding)。

设计原则:
- 单元测试绝不发起网络请求 / 连 Milvus。
- 通过 monkeypatch 替换 Config / LLMClient / MilvusStore / MiniMaxEmbedding。
- 集成测试用 marker 标记,CI 中默认跳过。
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """自动给所有测试注入假环境变量,防止 Config 初始化崩。"""
    env = {
        "MINIMAX_API_KEY": "test-key",
        "MINIMAX_GROUP_ID": "test-group",
        "MILVUS_URI": "http://localhost:19530",
        "EMBEDDING_DIM": "1536",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)


class FakeLLMClient:
    """替身 LLM:complete() 返回固定格式文本,chat() 返回固定答案。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def complete(self, prompt: str, **kwargs: Any) -> str:
        self.calls.append({"type": "complete", "prompt": prompt})
        if "意图类别" in prompt:
            return "factual"
        if "扩展" in prompt:
            return "扩展问题A\n扩展问题B\n扩展问题C"
        return "mock completion"

    def chat(self, messages: list[dict], **kwargs: Any) -> str:
        self.calls.append({"type": "chat", "messages": messages})
        return "这是一个基于参考资料的 mock 回答。"


@pytest.fixture()
def fake_llm() -> FakeLLMClient:
    return FakeLLMClient()


class FakeEmbedding:
    """替身 Embedding:返回固定维度向量。"""

    def __init__(self, dim: int = 8) -> None:
        self.dim = dim

    def _get_query_embedding(self, query: str) -> list[float]:
        return [0.1] * self.dim

    def _get_text_embedding(self, text: str) -> list[float]:
        return [0.2] * self.dim

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return self._get_text_embedding(text)


@pytest.fixture()
def fake_embedding() -> FakeEmbedding:
    return FakeEmbedding()


class FakeMilvusStore:
    """替身 Milvus:不连数据库,list_sources 返回空。"""

    def __init__(self) -> None:
        self._sources: dict = {}

    def has_collection(self) -> bool:
        return False

    def list_sources(self) -> dict:
        return self._sources

    @property
    def collection(self) -> MagicMock:
        m = MagicMock()
        m.get_collection_stats.return_value = {"row_count": 0}
        return m


@pytest.fixture()
def fake_store() -> FakeMilvusStore:
    return FakeMilvusStore()
