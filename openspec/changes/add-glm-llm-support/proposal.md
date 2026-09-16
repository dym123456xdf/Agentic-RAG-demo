# 支持 GLM 模型作为 LLM Provider

## Why

当前 `LLMClient` 硬编码 MiniMax 凭据,想换 GLM(智谱 / Z.ai)要改源码。GLM 与 MiniMax 一样走 OpenAI 兼容协议,只需在 Config 层做 provider 切换,LLM 通道可以完全复用。

Embedding 不在本次范围:embo-01 是 MiniMax 私有协议,GLM 的 embedding 接入是独立变更。

## What Changes

1. `Config` 新增 `LLM_PROVIDER`(minimax / glm,默认 minimax)与 GLM 凭据字段(`GLM_API_KEY` / `GLM_BASE_URL` / `GLM_MODEL`)
2. `Config` 新增 `llm_credentials()` 类方法:按 provider 返回 (api_key, base_url, model),provider 非法或缺 key 启动即报错(延续快速失败哲学)
3. `LLMClient` 改用 `Config.llm_credentials()`,删除 MiniMax 硬编码
4. 同步 `.env.bak` 模板 + `AGENTS.md` 环境准备

## Impact

- **文件**:`app/core/config.py`、`app/core/llm.py`、`.env.bak`、`AGENTS.md`
- **新增测试**:`tests/unit/test_llm_provider.py`(TDD,先红后绿)
- **风险**:低——默认行为不变(minimax),GLM 仅在显式配置后启用
