"""LLM Provider 切换逻辑单元测试(不发起任何网络请求)。"""
from __future__ import annotations

import pytest

from app.core.config import Config


class TestLLMCredentials:
    def test_default_provider_is_minimax(self) -> None:
        cred = Config.llm_credentials()
        assert cred["api_key"] == Config.MINIMAX_API_KEY
        assert cred["base_url"] == Config.MINIMAX_BASE_URL
        assert cred["model"] == Config.LLM_MODEL

    def test_glm_provider_returns_glm_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Config, "LLM_PROVIDER", "glm")
        monkeypatch.setattr(Config, "GLM_API_KEY", "glm-key-123")
        monkeypatch.setattr(Config, "GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
        monkeypatch.setattr(Config, "GLM_MODEL", "glm-4.6")

        cred = Config.llm_credentials()
        assert cred["api_key"] == "glm-key-123"
        assert cred["base_url"] == "https://open.bigmodel.cn/api/paas/v4"
        assert cred["model"] == "glm-4.6"

    def test_glm_provider_without_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Config, "LLM_PROVIDER", "glm")
        monkeypatch.setattr(Config, "GLM_API_KEY", "")

        with pytest.raises(RuntimeError, match="GLM_API_KEY"):
            Config.llm_credentials()

    def test_unknown_provider_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Config, "LLM_PROVIDER", "openai")

        with pytest.raises(RuntimeError, match="LLM_PROVIDER"):
            Config.llm_credentials()

    def test_glm_fast_role_returns_free_tier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Config, "LLM_PROVIDER", "glm")
        monkeypatch.setattr(Config, "GLM_API_KEY", "glm-key")
        monkeypatch.setattr(Config, "GLM_MODEL", "glm-5.3-flash")
        monkeypatch.setattr(Config, "GLM_FAST_MODEL", "glm-4.7-flash")

        fast = Config.llm_credentials(role="fast")
        main = Config.llm_credentials(role="main")
        assert fast["model"] == "glm-4.7-flash"
        assert main["model"] == "glm-5.3-flash"

    def test_minimax_fast_equals_main(self) -> None:
        assert Config.llm_credentials(role="fast")["model"] == Config.LLM_MODEL

    def test_unknown_role_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Config, "LLM_PROVIDER", "minimax")

        with pytest.raises(RuntimeError, match="main / fast"):
            Config.llm_credentials(role="turbo")


class TestLLMTierWiring:
    """预处理模块默认走 fast 档,生成走 main 档。"""

    def test_pre_query_defaults_to_fast_role(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        class Recorder:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr("app.rag.pre_query.LLMClient", Recorder)
        from app.rag.pre_query import QueryPreProcessor

        QueryPreProcessor()
        assert captured.get("role") == "fast"

    def test_generator_defaults_to_main_role(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        class Recorder:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr("app.rag.generator.LLMClient", Recorder)
        from app.rag.generator import Generator

        Generator()
        assert captured.get("role") == "main"

    def test_retriever_defaults_to_fast_role(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """retriever 里 fuser 的 query 变体生成属预处理,也走 fast。"""
        captured: dict = {}

        class Recorder:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr("app.rag.retriever.LLMClient", Recorder)
        monkeypatch.setattr("app.rag.retriever.load_existing_index", lambda: object())
        from app.rag.retriever import Retriever

        Retriever()
        assert captured.get("role") == "fast"
