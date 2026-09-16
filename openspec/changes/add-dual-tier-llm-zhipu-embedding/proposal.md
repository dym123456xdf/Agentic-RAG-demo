# 双模型分层 + 智谱 Embedding-3 适配器

## Why

1. **成本**:流水线 4 个 LLM 调用点里,意图识别 / 多轮改写 / 查询扩展(以及 retriever 的 query 变体生成)都是短输出轻量任务,用旗舰模型纯属浪费。GLM 免费档 `glm-4.7-flash`(200K 上下文,30B SOTA)足以覆盖,生成答案保留 `glm-5.3-flash` 保证质量。RAG 全链路成本可降 ~60%。
2. **架构一致性**:切换 Embedding 到智谱后,LLM 与 Embedding 同一家 provider、同一个 API Key;且 Embedding-3 是 OpenAI 兼容协议,适配成本远低于 MiniMax 私有协议。

## What Changes

1. **LLM 双档位**:`Config.llm_credentials(role)` 支持 `main`(生成)/ `fast`(预处理)两档;glm 下 main=GLM_MODEL(默认 glm-5.3-flash)、fast=GLM_FAST_MODEL(默认 glm-4.7-flash 免费档);minimax 下两档同模型
2. **角色接线**:`LLMClient` 新增 `role` 参数;`pre_query` 与 `retriever`(fuser 的 query 变体生成属预处理)用 `role="fast"`;`generator` 保持 `main`
3. **Embedding-3 适配器**:新增 `ZhipuEmbedding`(OpenAI 兼容 `/embeddings`,支持 dimensions=256/512/1024/2048);`get_embedding()` 工厂按 `EMBEDDING_PROVIDER` 分发;EMBEDDING_MODEL / EMBEDDING_DIM 默认值随 provider 联动(minimax: embo-01/1536,glm: embedding-3/1024)
4. **文档同步**:`.env.bak`、`AGENTS.md`(含"换 Embedding 必须清库重建"铁律)

## Impact

- **文件**:config.py / llm.py / pre_query.py / retriever.py / embedding.py / indexer.py / .env.bak / AGENTS.md
- **兼容性**:默认配置(minimax + embo-01)行为完全不变
- **风险**:中——Embedding 切换涉及向量空间更换,已在 AGENTS.md 特有坑中写明清库铁律
