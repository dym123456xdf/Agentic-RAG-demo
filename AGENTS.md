# AGENTS.md

> 遵循 [agents.md](https://agents.md) 标准,Codex / Cursor / Devin 等编程助手自动读取本文件。

5 段模块化 RAG 流水线:查询预处理 → 向量召回 → 重排 → 答案生成。
FastAPI + LlamaIndex + Milvus,Python ≥ 3.11,LLM/Embedding 用 MiniMax。
对话模型可切换:minimax(默认)/ glm(智谱),由 `LLM_PROVIDER` 决定;Embedding 固定 MiniMax embo-01(私有协议)。
glm 下 LLM 双档位:预处理(意图/改写/扩展/retriever 变体)走 `GLM_FAST_MODEL`(默认免费 glm-4.7-flash),生成走 `GLM_MODEL`(默认 glm-5.3-flash)。
Embedding 也可切 `EMBEDDING_PROVIDER=glm`(Embedding-3,OpenAI 兼容,默认 1024 维)。

## 常用命令

```bash
make install   # 安装依赖(含 dev 工具)
make test      # 单元测试;全部 mock,不需要 Milvus 在跑
make check     # lint + typecheck + test;提交前必须全绿
make run       # 启动服务 http://127.0.0.1:8000
```

- 测试不许打真实网络:LLM / Embedding / Milvus 的替身在 `tests/conftest.py`,新模块照此 mock。
- 需要真实 Milvus 的测试用 `@pytest.mark.integration` 标记,CI 默认不跑。

## 环境准备

1. Milvus:`docker run -d --name milvus-standalone -p 19530:19530 -p 9091:9091 milvusdb/milvus:v2.4-latest`
2. 复制 `.env.bak` 为 `.env`,填 `MINIMAX_API_KEY` + `MINIMAX_GROUP_ID`(两者必填)
3. 用 GLM 做对话模型:设 `LLM_PROVIDER=glm` 并填 `GLM_API_KEY`(embedding 仍走 MiniMax)
   - ⚠️ GLM Coding Plan(个人套餐)key 必须另设 `GLM_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4`,普通端点会报 1113 "余额不足"

## 架构与模块边界

```
app/core/  配置 + 外部客户端(LLM / Embedding / Milvus)。禁止业务逻辑。
app/rag/   流水线:pre_query → retriever → post → generator;入库走 loader → splitter → indexer。
app/api/   FastAPI 路由。只做"收请求 → 调 pipeline → 返响应"。
```

- 问答数据流:`api/chat → RAGPipeline.query → pre → retriever → post → generator`
- 入库数据流:`api/upload → RAGPipeline.ingest → loader.load → splitter.split → indexer.build_from_path`
- 一切配置走 `app/core/config.py` 的 `Config`;禁止在 rag/api 层直接 `os.getenv()`。

## 项目特有的坑(改代码前必读)

- **Milvus COSINE distance 语义反转**:distance 越小越相关,与 similarity 相反。`post.py` 的 cutoff 过滤依赖这一点,别把阈值方向搞反(默认 2.0 = 全放行)。
- **embo-01 协议不兼容 OpenAI**:请求体 `{texts, type}`,响应体 `{vectors[]}`,`GroupId` 必须放 URL query,漏了直接 400。适配器在 `app/core/embedding.py`,别用 OpenAI SDK 直接调。
- **M3 会输出 `<think>...</think>` 推理块**:所有 LLM 输出必须过 `app/core/llm.py` 的 `strip_thinking()`,新调用点别绕过它。
- **BGE 重排冷启动 ~13 秒**:模块级 lazy 单例在 `app/rag/post.py`;不要改成每请求加载,测试里直接 mock。
- **`Config` 在 import 时就读环境变量**:没配 key 时 `import app.core.config` 直接抛 RuntimeError。测试依赖进程启动前变量已存在——本地靠 `.env`,CI 在 workflow `env:` 注入。
- **MilvusVectorStore 不支持切 db**:llama-index 封装固定连默认 db,`rag_kb` 库的创建/切换在 `app/core/milvus_client.py` 单独用 MilvusClient 处理。
- **入库幂等靠文件名(source 字段)查重**:同名文件整篇跳过。改这段时注意 `stats.skipped_files` 的语义别破坏。
- **换 Embedding = 换向量空间**:切 `EMBEDDING_PROVIDER` 后必须清空 Milvus collection 重建,新旧向量混存检索会静默劣化;EMBEDDING_DIM 默认随 provider 联动(minimax 1536 / glm 1024),显式设置了 EMBEDDING_DIM 则以显式值为准。

## 变更规则(trigger → action)

- 改 `app/` 业务逻辑 → 先在 `openspec/changes/` 立项(`proposal.md` + `tasks.md`),然后 TDD;typo / log / 注释类琐碎改动除外
- 加改对外接口或行为 → 同步更新 `openspec/specs/` 对应能力的 `spec.md`
- 改 `Config` 的环境变量 → 同步更新 `.env.bak` 模板 + 本文件"环境准备"
- 加 Python 依赖 → 加到 `pyproject.toml` 正确的组(sentence-transformers/torch 进 `[rerank]`)
- 行为变更必须带测试,`make check` 全绿才能提交

提交格式 `<type>(<scope>): <描述>`,如 `feat(rag): 查询扩展去重`;范围取 rag / api / core / harness / spec。
