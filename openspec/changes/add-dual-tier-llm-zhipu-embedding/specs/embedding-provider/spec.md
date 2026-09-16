# embedding-provider 变更规格

## ADDED Requirements

### Requirement: Embedding Provider 切换
系统 SHALL 通过 `EMBEDDING_PROVIDER`(minimax / glm)选择向量化模型,默认 minimax。

#### Scenario: 切换到智谱 Embedding-3
- **GIVEN** EMBEDDING_PROVIDER=glm 且 GLM_API_KEY 已配置
- **WHEN** get_embedding() 被调用
- **THEN** 返回 ZhipuEmbedding 实例
- **AND** 默认模型 embedding-3、默认维度 1024(均可用显式 env 覆盖)

#### Scenario: 默认行为不变
- **GIVEN** 未设置 EMBEDDING_PROVIDER
- **WHEN** get_embedding() 被调用
- **THEN** 返回 MiniMaxEmbedding(embo-01,1536 维)

#### Scenario: 非法 provider 快速失败
- **WHEN** EMBEDDING_PROVIDER 为未知值
- **THEN** 抛出 RuntimeError 且信息列出可选项

### Requirement: 智谱嵌入请求契约
ZhipuEmbedding SHALL 按 OpenAI 兼容协议调用 `{GLM_BASE_URL}/embeddings`。

#### Scenario: 请求体
- **WHEN** 生成文本向量
- **THEN** POST body 含 model / input[] / dimensions=EMBEDDING_DIM
- **AND** Authorization 头为 Bearer GLM_API_KEY

#### Scenario: 缺 Key 快速失败
- **GIVEN** GLM_API_KEY 为空
- **WHEN** 构造 ZhipuEmbedding
- **THEN** 抛出 RuntimeError 且信息包含 GLM_API_KEY

### Requirement: 向量空间一致性
切换 EMBEDDING_PROVIDER SHALL 视为更换向量空间,必须清空 Milvus collection 重建。

#### Scenario: 文档化铁律
- **THEN** AGENTS.md 特有坑记录此约束,EMBEDDING_DIM 默认值随 provider 联动
