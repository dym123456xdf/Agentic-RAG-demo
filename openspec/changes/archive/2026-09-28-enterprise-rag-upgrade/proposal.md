# Proposal: enterprise-rag-upgrade

## Why

仓库 README 自述为 "FastAPI + llama-index + Milvus" 的单体 RAG 服务,而项目的原始需求文档描述的是一套企业级架构:LangGraph 编排、稠密+稀疏混合检索、HyDE/Web 搜索多路召回、断崖检测重排、MinIO 对象存储。当前代码只覆盖其中一小部分,且 MinIO、LangGraph、混合检索、HyDE、Web 搜索、断崖检测六块均未实现,导致检索召回质量受限、知识库无法承载多媒体文件、历史管理回溯困难。本次升级在保留 llama-index 与 MySQL 的前提下补齐这套能力,使服务达到需求文档描述的能力边界。

旧 Milvus collection 与本地 `uploads/`、`converted/` 目录视为 demo 数据,实施时直接清空重建。

## What Changes

- **新增 LangGraph 入库图**:把现有的"loader → splitter → indexer"线性流程包装成 `StateGraph`,节点化、可观测、可单测。
- **新增 LangGraph 查询图**:意图确认 → 多路召回(向量 / HyDE / Web) → RRF 融合 → 重排+断崖 → LLM 生成,以图状态为单一数据契约,节点可独立替换。
- **新增 BGE-M3 本地嵌入**:替换 embo-01 / embedding-3 双云端供应商,改为本地 FlagEmbedding 推理,单次产出 dense(1024)+ sparse 两套向量;llama-index `BaseEmbedding` 适配器接入 `Settings.embed_model`。
- **改造 Milvus collection schema**:由单一 dense 字段改为 dense(FLOAT_VECTOR 1024) + sparse(SPARSE_FLOAT_VECTOR)双字段;查询走 `pymilvus.MilvusClient.hybrid_search()`,库内 `WeightedRanker(0.8, 0.2)` 融合;停用 llama-index 的 `MilvusVectorStore` 包装,改为直接 pymilvus。
- **新增 MinIO 对象存储 + 后端代理路由**:原文件、MinerU 转换产物(md + images + assets)全部入桶;`/converted/<stem>/images/<file>` 由后端代理路由从 MinIO 流式回放;移除现有的 `/converted` static mount 与本地 `uploads/`、`converted/` 目录;桶策略设为 public-read 以兼容直连调试。
- **新增 MCP 网络搜索**:自建 MCP server(`mcp_server/server.py`)以 Brave Search API 为后端,暴露 `web_search` 工具;查询图 web 搜索节点作为 MCP client 调用。
- **新增 HyDE 假设性文档检索**:LLM 生成假设答案,与改写后 query 拼接后再走同一套混合检索,提升短查询召回率;触发条件由意图决定(explanatory / factual 开启,chitchat / creative 跳过)。
- **新增 RRF 融合节点**:多路召回结果按 RRF(k=60)融合,各路等权重,产出统一排序。
- **新增断崖检测重排**:重排后用"绝对阈值 + 相对阈值"双触发算法动态截断,替代固定 TopK,默认 `RERANK_GAP_ABS=1.0`、`RERANK_GAP_RATIO=0.3`(`Config` 暴露 `.env`);每条来源附 `confidence = sigmoid(score)` 供低置信度提示。
- **新增 SSE 阶段进度事件**:流式接口在检索图各节点完成时推送 `status` 事件(理解 → 召回 → 重排 → 生成),前端实时更新阶段文案,解决慢模型下首字前 40s+ 只见静态"检索中…"的体验问题。
- **新增闲聊分支**:`chitchat` 意图(寒暄/问候)不查知识库,直达重排空跑后由闲聊提示词直接对话(带历史、无参考资料约束)—— 不是所有输入都需要 RAG 检索。
- **前端来源展示调整**:参考来源块从答案上方移到答案之后,最多罗列 top3;低置信度提示仍置顶。
- **LLM 供应商支持 agnes**:`Config.llm_credentials` 在 minimax / glm 之外新增 agnes(agnes-3.0-flash,OpenAI 兼容),`.env` 切 `LLM_PROVIDER` 即换模型。
- **BREAKING**:切换 `EMBEDDING_PROVIDER` / Milvus schema / 静态文件路径,旧 collection 与本地数据全部作废,需要清库重建;前端 `/converted/` URL 契约保留。

## Capabilities

### New Capabilities

- `langgraph-orchestration`: 入库与查询两个 StateGraph 的装配、节点基类、状态契约;为整个 RAG 流水线提供 LangGraph 总编排。
- `hybrid-retrieval`: Milvus 显式 collection schema(dense + sparse)、BGE-M3 本地嵌入适配、pymilvus `hybrid_search()` 工具封装与库内加权融合。
- `multi-path-recall`: HyDE 假设文档生成、意图条件触发、MCP Web 搜索节点、RRF 倒数排名融合。
- `cliff-rerank`: BGE 重排后断崖检测动态截断(绝对 + 相对双阈值,`.env` 可调)。
- `minio-storage`: MinIO 客户端单例、桶初始化与公开读策略、原文件与转换产物落桶、后端代理路由替代 `/converted` static mount。

### Modified Capabilities

- `document-loading`: 第 6 条原 "FastAPI 挂载 `app.mount('/converted', StaticFiles(...))`" 失效 —— static mount 被 MinIO 后端代理路由替换;`converted/<stem>/` 不再是本地路径,而是 MinIO 对象前缀。
- `manage-page`: 第 3 条删除联动 —— `uploads/<name>` 与 `converted/<stem>/` 不再是本地目录,改为清理 MinIO 对应对象前缀;前端提示文案与状态同步逻辑不变。

## Impact

**代码侧**:

```
新增:
  app/core/bge_embedding.py         # BGE-M3 BaseEmbedding 适配
  app/core/milvus_hybrid.py         # pymilvus 直调 + 显式 schema + hybrid_search 工具
  app/core/minio_client.py          # MinIO 单例 + 桶初始化
  app/core/mcp_client.py            # 自建 MCP server 的客户端封装
  app/rag/state.py                  # 入库 / 查询图 TypedDict 状态契约
  app/rag/base.py                   # 节点基类(ABC + __call__)
  app/rag/ingest_graph.py           # 入库 StateGraph
  app/rag/query_graph.py            # 查询 StateGraph
  app/rag/nodes/                    # 14 个业务节点(查询图 7:preprocess / embedding_search /
                                    #   hyde_search / web_search / rrf_fuse / cliff_rerank /
                                    #   generate;入库图 7:entry / pdf_to_md / md_img /
                                    #   doc_split / item_name_recognition / bge_embedding /
                                    #   import_milvus)
  app/api/converted.py              # MinIO 后端代理路由(替换 static mount)
  mcp_server/server.py              # 自建 MCP server(Brave Search 后端)
  mcp_server/__main__.py            # MCP server 启动入口

重写:
  app/rag/pipeline.py               # LangGraph 薄壳,只暴露 query / query_stream / ingest
  app/rag/post.py                   # 改名为 cliff_rerank 节点,断崖算法搬进来
  app/core/config.py                # 追加 MinIO_* / MCP_* / BGE_* / RERANK_GAP_* 配置项
  app/api/upload.py                 # 走 MinIO(原文件 + 转换产物落桶)
  app/api/converted.py              # 新增:代理路由(替换 main.py 中的 static mount)
  main.py                           # 移除 /converted static mount,挂代理路由

废弃:
  app/core/embedding.py             # embo-01 / embedding-3 双供应商适配器废弃
  app/core/milvus_client.py         # llama-index MilvusVectorStore 包装废弃,改直调 pymilvus
  app/rag/retriever.py              # 改为 graph 节点,文件删除或仅留兼容垫片
```

**依赖侧**(实施时按需 `uv pip install` / `pip install`):

- `langgraph` — 图编排
- `FlagEmbedding` — BGE-M3 本地推理
- `pymilvus` — Milvus Python SDK(已是当前依赖,但本次改造直接用)
- `minio` — MinIO Python SDK
- `mcp` — Model Context Protocol Python SDK(自建 server 与 client)

**配置侧**(.env 新增):

```
# Milvus collection schema 变化(1024 dim 取代 1536)
EMBEDDING_DIM=1024

# BGE-M3 本地模型
BGE_M3_MODEL=BAAI/bge-m3
BGE_M3_DEVICE=mps       # mps / cuda / cpu

# MinIO
MINIO_ENDPOINT=127.0.0.1:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=rag-kb
MINIO_SECURE=false

# MCP self-host
MCP_SERVER_HOST=127.0.0.1
MCP_SERVER_PORT=8765
BRAVE_SEARCH_API_KEY=

# 断崖检测
RERANK_GAP_ABS=1.0
RERANK_GAP_RATIO=0.3
RERANK_MIN_TOPK=3
RERANK_MAX_TOPK=10
```

**数据侧**:

- 旧 Milvus collection(dense 1536 + dynamic fields)直接 `drop_collection` 后重建(dense 1024 + sparse 双字段)
- 本地 `uploads/`、`converted/` 目录删除,数据视为 demo 不迁移
- MySQL schema 不变(用户明确选择保留 MySQL)

**前端侧**:

- `/converted/<stem>/images/<file>` URL 契约保留,后端由代理路由从 MinIO 流式回放,图片渲染零改动
- SSE 新增 `status` 阶段事件,前端实时更新检索占位文案;参考来源块移至答案之后且最多展示 top3(`chat-streaming` 规格 delta)

**API 侧**:

- `POST /upload/files`、`POST /upload/clear`、`DELETE /upload/files/{name}`、`GET /upload/files`、`POST /upload/converted/{name}` 行为在内部路径上由本地改为 MinIO,HTTP 接口契约不变
- `POST /chat`、`POST /chat/stream` 接口契约不变;非流式与流式的 `meta` 事件中可附带 `recall_paths: ["dense", "hyde", "web"]` 字段,旧客户端忽略未知字段

**文档库影响**:

- README "技术栈" 章节需追加 LangGraph / BGE-M3 / MinIO / MCP 行
- README "注意事项" 章节需追加 "切换 EMBEDDING_PROVIDER / Milvus schema = 清空 collection 重建" 的强化警告
