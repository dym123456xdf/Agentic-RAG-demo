# CLAUDE.md

> Claude Code 项目级指令。**这是 Claude 工作的唯一真相源**。
> GitHub 访客/外部协作者请看 [README.md](./README.md);历史产品需求文档已归档到 [docs/requirements-archive.md](./docs/requirements-archive.md)。

## 0. 项目一句话

端到端的模块化 RAG 流水线。用户问题 → 查询预处理 → 向量召回 → 后处理(过滤+重排) → 答案生成 → 返回答案 + 来源。**5 段**,每段独立、可替换、可观测。

未来变更走 OpenSpec(`openspec/` 目录):改前先看有没有对应 `changes/<name>/`,没有就先 `/opsx:propose`。

---

## 1. 常用命令

**环境**:conda 环境 `rag`,Python ≥ 3.11。**没有 `requirements.txt`**,按需安装以下核心依赖:

```bash
pip install \
  fastapi \
  uvicorn \
  python-dotenv \
  pymilvus \
  llama-index \
  llama-index-vector-stores-milvus \
  llama-index-readers-file \
  sentence-transformers \
  torch
```

`MarkdownNodeParser` 随 `llama-index` 自带,导入路径 `llama_index.core.node_parser`。

**Milvus**(必须先起):
```bash
docker run -d --name milvus-standalone \
  -p 19530:19530 -p 9091:9091 \
  -v ~/milvus-data:/var/lib/milvus \
  milvusdb/milvus:v2.4-latest
curl http://localhost:9091/healthz   # → OK
```

**启动服务**:
```bash
mkdir -p uploads static/cache     # 首次克隆后手动建(.gitignore 排除了)
conda run -n rag uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
接口文档:http://127.0.0.1:8000/docs。

**接口自测**:
```bash
# 上传 + 入库(支持多文件)
curl -F "file=@./data/sample_kb.md" http://127.0.0.1:8000/upload/files

# 列出已入库文件
curl http://127.0.0.1:8000/upload/files

# 从服务器目录批量入库(指向 data/)
curl -X POST http://127.0.0.1:8000/upload/dir \
  -H "Content-Type: application/json" \
  -d '{"path":"data"}'

# 提问
curl -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" \
  -d '{"query":"什么是 embedding?","history":[]}'
```

**BGE 重排模型国内镜像**(首次冷启约 13 秒 + 下载 2.2 GB):
```bash
export HF_ENDPOINT=https://hf-mirror.com
```

---

## 2. 代码架构与模块职责

```
main.py                  FastAPI 入口,挂路由 + 静态页 + 启动日志
app/core/                基础能力(配置 / 大模型客户端 / 向量化 / Milvus)
app/rag/                 五段流水线
app/api/                 FastAPI 路由
```

**核心模块边界(每个文件单一职责)**:

| 文件 | 单一职责 |
|---|---|
| `app/core/config.py` | 从 `.env` 读 + 校验 + 集中暴露;不做网络、不实例化客户端;`_need()` 缺失即启动失败 |
| `app/core/embedding.py` | MiniMax `embo-01` 私有协议 → llama-index `BaseEmbedding` 适配器。**`_call(texts, type_="db"\|"query")` 区分两套编码空间,混用召回率暴跌** |
| `app/core/llm.py` | OpenAI 兼容协议调 M3;`strip_thinking()` 剥掉 `...` 推理块 |
| `app/core/milvus_client.py` | Milvus 连接 + 数据库 / 集合生命周期;`vector_store` 包成 llama-index `MilvusVectorStore`;进程内单例 `get_store()` |
| `app/rag/loader.py` | 文件 / 目录 → 文档对象。**`.md` 走直读不走非结构化读取器**(后者会把 `#` 头部抹掉);目录递归遍历。MinerU 入口尚未接通,见 `openspec/changes/wire-mineru-pipeline/` |
| `app/rag/splitter.py` | `MarkdownNodeParser` 按标题层级切段;非 md 退化为整篇一节 |
| `app/rag/indexer.py` | 加载 → 切分 → 入库。**幂等**:`list_sources()` 按文件名去重;只保留 `source` / `doc_id` 两字段(Milvus 不允许未注册字段);`load_existing_index()` 跳过重新向量化 |
| `app/rag/pre_query.py` | 三步合一(一次提示跑三件事免得多次大模型调用):多轮改写 + 意图识别 + 查询扩展。`HISTORY_WINDOW=3` 最近三轮 |
| `app/rag/retriever.py` | 默认 `QueryFusionRetriever`(`reciprocal_rerank` 模式)对扩展查询分别召回融合;数量不足时用改写后的查询兜底。**注意**:当前实现把 `processed.original` 喂给 fuser,`rewritten` / `expanded` 仅作兜底 — 见 `openspec/changes/use-processed-query-in-retriever/` |
| `app/rag/post.py` | 1) Milvus 余弦距离阈值过滤(值越小越相关)2) BGE 交叉编码器重排取前 N。模块级懒加载单例 `_BGE`,Apple Silicon 走 `mps` |
| `app/rag/generator.py` | 拼上下文 + 大模型出答案 + 来源列表;**严禁编造**(`SYSTEM` 提示强制) |
| `app/rag/pipeline.py` | 端到端编排 `pre_query → retriever → post → generator`,附加 `meta` 调试信息 |
| `app/api/upload.py` | 上传 + 列文件 + 清空;`get_pipeline()` 进程内单例避免每次请求重载 BGE |
| `app/api/chat.py` | Pydantic 模型 + `POST /chat` |

---

## 3. 关键设计取舍(改这块前必读)

**`embo-01` 协议跟 OpenAI 不兼容**,三处硬差异(详见 `app/core/embedding.py` 头部注释):
1. 请求体字段名不同(`texts` / `type`,不是 `input`)
2. `GroupId` 必须走 URL 查询参数,不能放请求体
3. 响应是 `vectors[]`,不是 `data[].embedding`

**入库与检索必须用不同编码**:`_get_text_embedding` 强制 `type_="db"`、`_get_query_embedding` 强制 `type_="query"`。**混用召回率暴跌**(能跑通但结果很差)。九成九的"PDF 入库召回 0"都源自这里写反。

**Markdown 按标题切,不用定长切**:保语义完整。`MarkdownNodeParser` 会塞 `header_path` / `header` 等额外元数据,`indexer.py` 入库前显式清洗只留 `source` + `doc_id`,否则 Milvus 报未注册字段。

**Milvus 余弦距离 ∈ [0, 2],值越小越相关**。`SIMILARITY_CUTOFF=2.0` 默认"全过",粗筛全交给 BGE 精修。llama-index 的 `SimilarityPostprocessor` 假设分数越大越相关,语义反了,**`post.py` 不用它**,手写距离阈值过滤。

**M3 输出 `...` 推理块**:`llm.py` 的 `strip_thinking()` 全局剥掉,避免上游收到噪声。

**MilvusVectorStore 的 db_name 限制**:`app/core/milvus_client.py` 把 `MilvusClient` 包成 llama-index `MilvusVectorStore` 时,`MILVUS_DB=rag_kb` **实际不生效**(数据写到 default DB)。`MILVUS_URI` 一定,数据隔离只能靠 `MILVUS_COLLECTION` 字段区分。修复方案见 `openspec/changes/fix-milvus-db-name-ignored/`。

---

## 4. .env 必填项

```ini
MINIMAX_API_KEY=sk-cp-...
MINIMAX_GROUP_ID=...            # embo-01 必填,丢 URL 查询参数,不传报 400
MINIMAX_BASE_URL=https://api.minimaxi.com/v1
LLM_MODEL=MiniMax-M3
EMBEDDING_MODEL=embo-01
EMBEDDING_DIM=1536
MILVUS_URI=http://localhost:19530
MILVUS_DB=rag_kb                 # 当前未生效,见 fix-milvus-db-name-ignored
MILVUS_COLLECTION=personal_kb
```

可选(都有默认值):`TOP_K=10` / `RERANK_TOP_N=5` / `SIMILARITY_CUTOFF=2.0` / `RERANK_MODEL=BAAI/bge-reranker-v2-m3` / `HOST` / `PORT=8000` / `UPLOAD_DIR=./uploads` / `MAX_UPLOAD_MB=50`。

MinerU 开关(`MINERU_ENABLED=false` 默认 / `MINERU_BIN` / `MINERU_OUTDIR=./converted` / `MINERU_TIMEOUT_S=600`)已在 `config.py` 就位但 **loader/upload 未接通**,开关打开也无效果。要接通按 `openspec/changes/wire-mineru-pipeline/tasks.md` 走。

---

## 5. 调试清单

- 启动报 `环境变量 XXX 未配置` → 根目录缺 `.env` 或字段缺失
- Milvus `14 UNAVAILABLE` → `docker ps | grep milvus` 看容器在不在;`MILVUS_URI` 必须 `http://localhost:19530`
- 首启几十秒慢 → BGE 模型首次下载 2.2 GB;设 `HF_ENDPOINT=https://hf-mirror.com`
- PDF 入库后召回 0 → 九成九是 `db` / `query` 写反;检查 `app/rag/indexer.py` 是否走 `_get_text_embedding`
- Apple Silicon `sentence-transformers` 报错 → `pip install torch` 装 MPS 版本;`post.py` 已自动 `device="mps"`
- 数据"看起来入库了"但查询召回的是别库 → `MILVUS_DB` 配置实际未生效,见上"MilvusVectorStore 的 db_name 限制"

---

## 6. 变更规范(OpenSpec)

所有非琐碎改动都从 `openspec/changes/<name>/` 开始:

```
openspec/
├── AGENTS.md           Claude 在此目录的工作指令
├── project.md          项目上下文
├── specs/              已部署能力规格(permanent)
│   ├── query-understanding/
│   ├── hybrid-retrieval/
│   ├── reranking/
│   ├── answer-generation/
│   ├── document-indexing/
│   └── api-surface/
└── changes/            进行中的变更提案
    ├── reconcile-docs/             ✓ 已实现(本次整理)
    ├── wire-mineru-pipeline/       提案中
    ├── fix-milvus-db-name-ignored/ 提案中
    └── use-processed-query-in-retriever/ 提案中
```

每个 change 文件夹:
- `proposal.md` — 为什么、改什么、影响范围
- `tasks.md` — 实现清单(checkbox)
- `design.md` — 技术取舍(可选但推荐)
- `specs/<capability>/spec.md` — **仅当能力变化时**才写,描述未来状态(`## ADDED Requirements`)
- `.openspec.yaml` — 元数据(`schema: spec-driven`, `created: <date>`)

spec.md 写法:
- `### Requirement: <动词短语>`
- `#### Scenario: <短句>` + `- **WHEN** ... / - **THEN** ... / - **AND** ...`
- 行为优先,库名/类名放 design.md

**改 app/ 代码之前**:先 `cat openspec/changes/*/proposal.md` 看有没有相关提案;有就更新对应 change,没有就 `/opsx:propose <name>`(需要先装 `npm i -g @fission-ai/openspec`)。

---

## 7. 指针

- 架构图 / 模块表 / 取舍表完整版 → 本文件 §2、§3
- 上传 / 对话 / 列表接口契约 → `openspec/specs/api-surface/spec.md`
- 检索 / 重排 / 生成能力契约 → `openspec/specs/{hybrid-retrieval,reranking,answer-generation}/spec.md`
- 历史产品需求(只读) → `docs/requirements-archive.md`
- GitHub 访客快速入门 → `README.md`
