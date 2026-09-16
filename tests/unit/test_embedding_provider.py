"""Embedding Provider 工厂与智谱 Embedding-3 适配器单元测试(不发真实网络请求)。"""
from __future__ import annotations

from typing import Any

import pytest

from app.core.config import Config
from app.core.embedding import MiniMaxEmbedding, ZhipuEmbedding, get_embedding


class TestGetEmbeddingFactory:
    def test_default_returns_minimax(self) -> None:
        assert isinstance(get_embedding(), MiniMaxEmbedding)

    def test_glm_provider_returns_zhipu(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Config, "EMBEDDING_PROVIDER", "glm")
        monkeypatch.setattr(Config, "GLM_API_KEY", "glm-key")
        assert isinstance(get_embedding(), ZhipuEmbedding)

    def test_unknown_provider_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Config, "EMBEDDING_PROVIDER", "openai")

        with pytest.raises(RuntimeError, match="EMBEDDING_PROVIDER"):
            get_embedding()


class TestZhipuEmbedding:
    @pytest.fixture()
    def emb(self, monkeypatch: pytest.MonkeyPatch) -> ZhipuEmbedding:
        monkeypatch.setattr(Config, "EMBEDDING_DIM", 1024)
        monkeypatch.setattr(Config, "EMBEDDING_MODEL", "embedding-3")
        monkeypatch.setattr(Config, "GLM_API_KEY", "test-zhipu-key")
        monkeypatch.setattr(Config, "GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
        return ZhipuEmbedding()

    def test_request_url_body_and_parse(
        self, emb: ZhipuEmbedding, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_post(url: str, **kwargs: Any):
            captured["url"] = url
            captured["json"] = kwargs.get("json")
            captured["headers"] = kwargs.get("headers")

            class Resp:
                def raise_for_status(self) -> None:
                    pass

                def json(self) -> dict:
                    return {"data": [{"embedding": [0.5] * 1024, "index": 0}]}

            return Resp()

        monkeypatch.setattr("app.core.embedding.requests.post", fake_post)
        vec = emb._get_text_embedding("你好世界")

        assert vec == [0.5] * 1024
        assert captured["url"] == "https://open.bigmodel.cn/api/paas/v4/embeddings"
        assert captured["json"]["model"] == "embedding-3"
        assert captured["json"]["input"] == ["你好世界"]
        assert captured["json"]["dimensions"] == 1024
        assert captured["headers"]["Authorization"] == "Bearer test-zhipu-key"

    def test_missing_key_fails_fast(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Config, "GLM_API_KEY", "")

        with pytest.raises(RuntimeError, match="GLM_API_KEY"):
            ZhipuEmbedding()

    def test_api_error_raises(self, emb: ZhipuEmbedding, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_post(url: str, **kwargs: Any):
            class Resp:
                def raise_for_status(self) -> None:
                    pass

                def json(self) -> dict:
                    return {"error": {"code": "1210", "message": "api key 缺失"}}

            return Resp()

        monkeypatch.setattr("app.core.embedding.requests.post", fake_post)

        with pytest.raises(RuntimeError, match="embedding"):
            emb._get_text_embedding("hello")
