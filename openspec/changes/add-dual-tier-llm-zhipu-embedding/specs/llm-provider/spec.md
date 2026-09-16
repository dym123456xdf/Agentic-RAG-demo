# llm-provider 双档位增量

## ADDED Requirements

### Requirement: LLM 角色双档位
系统 SHALL 支持按角色(role)选择对话模型:main(答案生成)/ fast(预处理),由各调用点显式声明。

#### Scenario: glm 双档位
- **GIVEN** LLM_PROVIDER=glm
- **WHEN** 分别请求 role=fast 与 role=main 的凭据
- **THEN** fast 返回 GLM_FAST_MODEL(默认 glm-4.7-flash)
- **AND** main 返回 GLM_MODEL(默认 glm-5.3-flash)

#### Scenario: minimax 无分档
- **GIVEN** LLM_PROVIDER=minimax(默认)
- **WHEN** 请求 role=fast
- **THEN** 返回与 main 相同的模型(MiniMax 无免费档)

#### Scenario: 非法角色快速失败
- **WHEN** 传入 role=turbo 等未定义值
- **THEN** 抛出 RuntimeError 且信息列出可选 main / fast

### Requirement: 预处理调用点使用 fast 档
意图识别 / 多轮改写 / 查询扩展 / retriever 的 query 变体生成 SHALL 使用 role=fast。

#### Scenario: 接线验证
- **WHEN** 构造 QueryPreProcessor / Retriever
- **THEN** 其内部 LLMClient 以 role="fast" 创建

### Requirement: 生成调用点使用 main 档
答案生成 SHALL 使用 role=main。

#### Scenario: 接线验证
- **WHEN** 构造 Generator
- **THEN** 其内部 LLMClient 以 role="main" 创建
