

# Agentic-RAG-demo(企业版)

基于 **FastAPI + llama-index + LangGraph + Milvus + MinIO + MCP** 的个人/团队知识库问答服务:上传 PDF / Markdown / Word / PPT 等文档,即可通过网页或 API 进行有据可查的问答 —— 答案只基于库内资料 + Web 检索补充,并附来源引用与置信度提示。

核心特点:

- **LangGraph 编排**:入库与查询均跑在 `StateGraph` 上,节点化、可观测、可单测;业务逻辑全在各节点
- **稠密 + 稀疏混合检索**:BGE-M3 一次推理产出 dense(1024)+ sparse 双向量,Milvus `hybrid_search()` + `WeightedRanker(0.8, 0.2)` 库内融合
- **多路召回**:意图条件触发 HyDE(假设性文档检索)+ MCP Web 搜索(Brave Search 后端),三路 RRF 倒数排名融合
- **断崖检测重排**:BGE-reranker-v2-m3 重排后用「绝对 + 相对双阈值」动态截断,替代固定 TopK
- **MinIO 对象存储**:原文件与 MinerU 转换产物(md + images + assets)全部入桶,前端 URL 契约保留(后端代理路由从 MinIO 流式回放)
- **MCP 自建服务**:Brave Search 工具以 stdio 传输由 LangGraph 节点内调用,部署简化
- **入库幂等**:同名文件前端预检拦截,不重复消耗 embedding
- **流式问答 + 低置信度友情提示**:SSE 推送 meta → delta* → done,前端先看到来源,逐字出答案

## 架构

```
                +-----------------------------+
                |  FastAPI                    |
                |  /upload /converted /chat   |
                +--------------+--------------+
                               |
                               v
        +----------------------+-----------------------+
        |            app.rag.pipeline                  |
        |     LangGraph 薄壳:query/query_stream/ingest|
        +-----+-------------------+-------------------+
              |                   |
              v                   v
       +------+------+    +------+------+
       | 查询图      |    | 入库图      |
       | preprocess  |    | entry ...   |
       |   ↓         |    | import_milvus|
       | 三路并行召回 |    +-------------+
       |   ↓         |
       | rrf_fuse    |
       | cliff_rerank|
       | generate    |
       +-------------+
```

| 模块 | 位置 | 职责 |
|------|------|------|
| 配置中心 | `app/core/config.py` | 读取 `.env`,快速失败;LLM/Embedding/MinIO/MCP/重排/特性开关 |
| LLM 客户端 | `app/core/llm.py` | OpenAI 兼容协议(minimax / glm),剥离 `<think>` 推理块 |
| BGE-M3 嵌入 | `app/core/bge_embedding.py` | FlagEmbedding 本地推理,dense(1024)+ sparse 双向量 |
| Milvus 混合 | `app/core/milvus_hybrid.py` | pymilvus 直调;显式 schema(dense + sparse);hybrid_search 工具 |
| MinIO 客户端 | `app/core/minio_client.py` | 单例 + 桶初始化(public-read)+ 常用对象操作 |
| MCP 客户端 | `app/core/mcp_client.py` | stdio 拉起 mcp_server 子进程 |
| MCP 自建服务 | `mcp_server/server.py` | Brave Search 后端的 web_search 工具 |
| LangGraph 节点 | `app/rag/nodes/` | 入库 7 + 查询 7 节点,继承 `BaseNode(ABC)` |
| LangGraph 图 | `app/rag/ingest_graph.py` / `query_graph.py` | StateGraph 装配与编译 |
| 状态契约 | `app/rag/state.py` | TypedDict + 工厂函数 |
| 节点基类 | `app/rag/base.py` | `BaseNode(ABC)` + `__call__` 统一日志/异常 |
| 管线薄壳 | `app/rag/pipeline.py` | 对外暴露 3 个入口函数 |
| API 路由 | `app/api/upload.py` / `chat.py` / `sessions.py` / `converted.py` | 业务入口 |
| 前端 | `static/index.html` | 单页界面 |

## 快速开始

### 前置要求

- Python 3.11(推荐 conda 管理环境)
- 一个运行中的 [Milvus](https://milvus.io)(默认 `http://localhost:19530`,可用 Docker 单机版)
- 一个运行中的 [MinIO](https://min.io)(默认 `127.0.0.1:9000`,桶 `rag-kb`)
- 本地 `BAAI/bge-m3` 模型(可从 ModelScope / HuggingFace 下载)
- MiniMax 或 智谱 GLM 的 API Key

### 1. 启动外部服务

```bash
# MinIO(对象存储)
docker run -d --name minio -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio server /data --console-address ":9001"

# Milvus(向量库,标准单机版)
docker compose -f <your-milvus-compose> up -d

# BGE-M3 模型(可选放本地;如未放,FlagEmbedding 会自动下载)
python -c "from FlagEmbedding import BGEM3FlagModel; BGEM3FlagModel('BAAI/bge-m3')"
```

### 2. 安装依赖

本仓库未附带依赖清单,依赖装在 conda 环境 `rag` 中。核心依赖如下:

```bash
conda run -n rag pip install \
  fastapi "uvicorn[standard]" \
  llama-index llama-index-llms-openai-like \
  pymilvus \
  langgraph FlagEmbedding \
  minio mcp httpx \
  sentence-transformers python-dotenv requests
```

### 3. 配置 `.env`

```bash
# ===== LLM(MiniMax / 智谱二选一)=====
MINIMAX_API_KEY=你的key
LLM_PROVIDER=minimax

# ===== Embedding:本地 BGE-M3(企业版统一)=====
EMBEDDING_PROVIDER=bge-m3
EMBEDDING_DIM=1024
BGE_M3_MODEL=BAAI/bge-m3
BGE_M3_DEVICE=mps

# ===== Milvus =====
MILVUS_URI=http://localhost:19530
MILVUS_DB=rag_kb
MILVUS_COLLECTION=rag_kb_chunks

# ===== MinIO =====
MINIO_ENDPOINT=127.0.0.1:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=rag-kb
MINIO_SECURE=false

# ===== MCP(可选,Web 搜索)=====
MCP_SERVER_HOST=127.0.0.1
MCP_SERVER_PORT=8765
BRAVE_SEARCH_API_KEY=
WEB_SEARCH_ENABLED=false

# ===== 断崖检测 =====
RERANK_GAP_ABS=1.0
RERANK_GAP_RATIO=0.3
RERANK_MIN_TOPK=3
RERANK_MAX_TOPK=10

# ===== 特性 =====
HYDE_ENABLED=true
MINERU_ENABLED=false
```

### 4. 启动

```bash
conda run -n rag uvicorn main:app --host 127.0.0.1 --port 8011 --reload
```

打开 http://127.0.0.1:8011/static/index.html 即可使用网页;上传文档 → 提问。

> MCP 子进程(`python -m mcp_server`)由 web_search 节点按需 stdio 拉起,无需手动启动。

## 使用

### API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/upload/files` | multipart 上传文件并入库 |
| GET | `/upload/files` | 列出已入库文件及各自 chunk 数 |
| DELETE | `/upload/files/{name}` | 联动删除:Milvus + MinIO 原文件 + MinIO 转换产物 |
| POST | `/upload/clear` | 清空 Milvus collection(drop + 重建) |
| GET | `/converted/{stem:path}` | 转换产物代理路由(从 MinIO 流式回放,前端零改动) |
| POST | `/chat` | 提问,返回答案 + 来源 + meta |
| POST | `/chat/stream` | SSE 流式问答(meta → delta* → done) |
| POST | `/sessions` | 创建会话 |
| GET | `/sessions` | 列全部会话 |

```bash
# 上传并入库
curl -X POST http://127.0.0.1:8011/upload/files -F "files=@./doc.pdf"

# 提问
curl -X POST http://127.0.0.1:8011/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "文档里讲了什么?", "session_id": 1}'
```

## 配置说明

所有配置均在项目根 `.env`,缺必填项时启动即报错(快速失败)。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_PROVIDER` | `minimax` | 对话模型供应商:`minimax` / `glm` |
| `EMBEDDING_PROVIDER` | `bge-m3` | 嵌入供应商(企业版统一本地 BGE-M3;旧 embo-01 / embedding-3 已废弃) |
| `BGE_M3_MODEL` / `BGE_M3_DEVICE` | `BAAI/bge-m3` / `mps` | 本地模型路径与设备(mps / cuda / cpu) |
| `MILVUS_URI` / `MILVUS_DB` / `MILVUS_COLLECTION` | `http://localhost:19530` / `rag_kb` / `rag_kb_chunks` | Milvus 连接 |
| `AUTO_REBUILD_SCHEMA` | `true` | 旧 schema 检测到时是否自动 drop 重建 |
| `MINIO_*` | — | MinIO endpoint / 凭据 / 桶名 / secure |
| `MCP_SERVER_HOST` / `MCP_SERVER_PORT` / `BRAVE_SEARCH_API_KEY` | `127.0.0.1` / `8765` / 空 | MCP 与 Web 搜索 |
| `RERANK_GAP_ABS` / `RERANK_GAP_RATIO` / `RERANK_MIN_TOPK` / `RERANK_MAX_TOPK` | `1.0` / `0.3` / `3` / `10` | 断崖检测双阈值与边界 |
| `RRF_K` | `60` | RRF 倒数排名融合参数 |
| `HYDE_ENABLED` / `WEB_SEARCH_ENABLED` | `true` / `false` | HyDE / Web 召回开关 |
| `MINERU_ENABLED` / `MINERU_BIN` / `MINERU_OUTDIR` | `false` / conda bin / `converted` | MinerU 解析(staging 目录) |
| `TOP_K` / `RERANK_TOP_N` | `20` / `5` | 召回数 / 默认精排保留数 |
| `CONFIDENCE_THRESHOLD` | `0.6` | 低置信度友情提示阈值(sigmoid 后 0-1) |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | 服务监听地址 |
| `MAX_UPLOAD_MB` | `50` | 单文件大小上限 |

## 注意事项

- **切换 `EMBEDDING_PROVIDER` / Milvus schema = 清空 collection 重建**:dense 维度 1024(BGE-M3 固定)+ sparse 双字段;旧单 dense collection 会被自动 drop 重建(`AUTO_REBUILD_SCHEMA=true`),视为 demo 数据丢失
- **同名文件不会重新入库**:前端预检拦截;如需重新入库,改名重传或 `POST /upload/clear`
- **MinIO 是唯一持久化载体**:原文件与 MinerU 转换产物全部落桶,本地 `uploads/` / `converted/` 不再被业务路径写入(MinerU staging 临时目录除外)
- **Web 搜索结果不入 Milvus**:仅作为本次回答 `sources` 的一次性来源,`source_type == "web"`
- **COSINE 距离越小越相关**:与"相似度越大越相关"语义相反;断崖检测 / 置信度计算都基于 sigmoid(score) 反转后的 0-1 标度
- **预处理与生成的 LLM 输出中的 `<think>` 推理块已自动剥离**
- **首次问答时会自动从 HuggingFace 下载 `BAAI/bge-reranker-v2-m3` 重排模型(约 2 GB)**
