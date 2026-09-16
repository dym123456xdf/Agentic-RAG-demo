# llm-provider 变更规格

## ADDED Requirements

### Requirement: 对话模型 Provider 切换
系统 SHALL 通过环境变量 `LLM_PROVIDER` 选择对话模型提供方(minimax / glm),默认 minimax。

#### Scenario: 切换到 GLM
- **GIVEN** .env 配置 `LLM_PROVIDER=glm` 且 `GLM_API_KEY` 非空
- **WHEN** LLMClient 初始化
- **THEN** 使用 GLM_BASE_URL(默认 https://open.bigmodel.cn/api/paas/v4)与 GLM_MODEL(默认 glm-4.6)
- **THEN** 使用 GLM_BASE_URL(默认 https://open.bigmodel.cn/api/paas/v4)与 GLM_MODEL(默认 glm-5.3-flash)

#### Scenario: GLM 缺 Key 快速失败
- **GIVEN** `LLM_PROVIDER=glm` 但 `GLM_API_KEY` 为空
- **WHEN** LLMClient 初始化
- **THEN** 抛出 RuntimeError 且信息包含 GLM_API_KEY

#### Scenario: 非法 Provider 快速失败
- **WHEN** `LLM_PROVIDER` 不是 minimax 或 glm
- **THEN** 抛出 RuntimeError 且信息列出可选项

#### Scenario: 默认行为不变
- **GIVEN** 未设置 LLM_PROVIDER
- **WHEN** LLMClient 初始化
- **THEN** 行为与改动前一致(MiniMax 凭据 + MiniMax-M3)

### Requirement: Embedding 不受 Provider 切换影响
Embedding SHALL 始终使用 MiniMax embo-01(私有协议),不随 LLM_PROVIDER 切换。
