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
