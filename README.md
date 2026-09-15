# Agentic-RAG-demo

端到端的模块化 RAG 流水线:把"基于自有资料回答问题"拆成 **查询预处理 → 向量召回 → 重排 → 答案生成** 四段,每段可独立替换、可观测。

- **LLM**:`MiniMax-M3`(OpenAI 兼容协议)
- **Embedding**:`embo-01`(MiniMax,**协议与 OpenAI 不兼容**,已封装适配器)
- **向量库**:Milvus(standalone,Docker 部署)
- **重排**:`BAAI/bge-reranker-v2-m3`(本地 MPS/CPU)
- **运行时**:Python ≥ 3.11,FastAPI

---

## 1. 快速开始

### 1.1 准备环境

```bash
# Python ≥ 3.11(项目用 conda 环境 `rag`)
conda create -n rag python=3.11 -y
conda activate rag

# 克隆后,在项目根目录装依赖
pip install -r requirements.txt  # 见下方"依赖"段,如未提供可手动装核心包
```

### 1.2 启动 Milvus(必须)

服务依赖 Milvus,Docker 起一个 standalone:

```bash
docker run -d --name milvus-standalone \
  -p 19530:19530 -p 9091:9091 \
  -v ~/milvus-data:/var/lib/milvus \
  milvusdb/milvus:v2.4-latest
```

确认可达:`curl http://localhost:9091/healthz` 返回 `OK`。

### 1.3 写 `.env`

**项目根目录**下创建 `.env`(已被 `.gitignore` 排除,不会上推):

```ini
# LLM(对话 / 意图 / 改写 / 答案生成)
MINIMAX_API_KEY=sk-cp-你的key
MINIMAX_BASE_URL=https://api.minimaxi.com/v1
MINIMAX_GROUP_ID=你的group_id
LLM_MODEL=MiniMax-M3

# Embedding(必填 GroupId,丢在 URL query,不传 400)
EMBEDDING_MODEL=embo-01
EMBEDDING_DIM=1536

# Milvus
MILVUS_URI=http://localhost:19530
MILVUS_DB=rag_kb
MILVUS_COLLECTION=personal_kb

# 检索 / 重排
TOP_K=10
RERANK_TOP_N=5
SIMILARITY_CUTOFF=2.0
RERANK_MODEL=BAAI/bge-reranker-v2-m3

# 服务 / 上传
HOST=127.0.0.1
PORT=8000
UPLOAD_DIR=./uploads
MAX_UPLOAD_MB=50
```

### 1.4 建本地目录 + 启动服务

```bash
# clone 后 .gitignore 排除了 uploads/ 和 static/cache/,需手动建
mkdir -p uploads static/cache

# 启动
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

浏览器打开 `http://127.0.0.1:8000` 即可使用 Web 界面。

---

## 2. 架构

```
用户问题 → 查询预处理 → 文档召回 → 后处理(过滤+重排) → 答案生成 → 返回答案+来源
```

| 模块 | 职责 | 文件 |
|---|---|---|
| 配置中心 | 从 `.env` 读 + 校验 + 集中暴露 | `app/core/config.py` |
| Embedding 适配 | MiniMax 私有协议 → llama-index BaseEmbedding | `app/core/embedding.py` |
| LLM 客户端 | OpenAI 兼容协议封装 | `app/core/llm.py` |
| Milvus 客户端 | 连接 + collection 初始化 | `app/core/milvus_client.py` |
| 文档加载 | Markdown / PDF / DOCX 解析 | `app/rag/loader.py` |
| 文档切分 | 按 Markdown 标题层级切段 | `app/rag/splitter.py` |
| 索引构建 | 加载 → 切分 → 入库 → 索引对象 | `app/rag/indexer.py` |
| 查询预处理 | 意图识别 + 多轮改写 + 查询扩展 | `app/rag/pre_query.py` |
| 文档召回 | 纯向量 / QueryFusion 混合检索 | `app/rag/retriever.py` |
| 检索后处理 | 相似度阈值 + cross-encoder 重排 | `app/rag/post.py` |
| 答案生成 | 拼上下文 + LLM 生成 + 来源列表 | `app/rag/generator.py` |
| 端到端编排 | 5 段流水线串起来 | `app/rag/pipeline.py` |
| API 路由 | 上传 + 对话 | `app/api/upload.py` `app/api/chat.py` |

---

## 3. API

启动后访问 `http://127.0.0.1:8000/docs` 看 Swagger。

### 3.1 上传文档并构建索引

```bash
curl -F "file=@./data/sample_kb.md" http://127.0.0.1:8000/upload
```

支持:`.pdf` `.md` `.markdown` `.docx` `.pptx` `.txt`(白名单在 `config.ALLOWED_EXTS`)。

### 3.2 提问

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "什么是 embedding?",
    "history": []
  }'
```

返回 JSON:`answer`(文本) + `sources`(编号 / 内容预览 / 相关度分数 / 来源文件)。

---

## 4. 关键设计取舍

**为什么 embedding 必须自写适配器,不能直接用 OpenAI 风格封装?**
MiniMax 的 `/v1/embeddings` 端点路径虽然同名,但跟 OpenAI 协议**不兼容**,三处硬差异:
1. 请求体字段名不同(`texts` / `type`,不是 `input`)
2. 租户标识 `GroupId` 必须通过 URL query string 传,不能放 body
3. 响应结构不同(返回 `vectors` 字段,不是 `data[].embedding`)

直接用通用封装会:**400 invalid params → 401 鉴权 → 维度不匹配写入失败 → 检索永远召回 0 条** 连锁爆雷。封装在 `app/core/embedding.py` 一个文件里封死。

**为什么入库和检索要区分编码模式?**
MiniMax 把"被检索文档"和"查询语句"用两套不同编码空间(`db` / `query` 模式)。**混用会导致召回率显著下降**(虽然能跑通,但结果很差)。`_call(texts, type_="db"|"query")` 封装了这两层语义。

**为什么用 Markdown 标题切分,不用固定长度?**
固定长度会从句子中间切断丢失语义。Markdown 文档天然有标题层级结构,按标题切分保证每段语义完整,语义匹配更准。

**为什么重排的相似度阈值默认 2.0(COSINE distance 上限)?**
distance ∈ [0, 2],2.0 = "全过",把粗筛放开交给 BGE 重排做精修。如发现噪音太多可下调。

**为什么对话历史只取最近 3 条?**
历史越长改写 prompt 越长,token 消耗多 + 延迟高。实测最近 3 轮足够覆盖上下文指代,再多收益递减。

---

## 5. 常见问题

**Q1:`uvicorn main:app` 启动报 `RuntimeError: 环境变量 MINIMAX_API_KEY 未配置`**
→ 项目根目录没 `.env` 或字段缺失,按 1.3 段复制。

**Q2:Milvus 连不上 / 报 `14 UNAVAILABLE`**
→ 确认 Docker 容器在跑(`docker ps | grep milvus`);`MILVUS_URI` 填 `http://localhost:19530`。

**Q3:首次启动很慢(几十秒)**
→ BGE 重排模型约 2.2GB,首次加载需要从 HuggingFace 下载,加载一次后复用。可提前 `export HF_ENDPOINT=https://hf-mirror.com` 用国内镜像。

**Q4:上传 PDF 后检索召回 0 条**
→ 99% 是 embedding 编码模式混用(`db` / `query` 写反),或文档切分后段落全是空。检查 `app/rag/indexer.py` 是否正确调用 `_get_text_embedding`(用 `db` 模式)。

**Q5:Apple Silicon(M1/M2/M3)上 sentence-transformers 报错**
→ `pip install torch` 装 MPS 版本,然后确认 `device="mps"` 已设。CPU 跑也可用,只是慢。

---

## 6. 目录结构

```
Agentic-RAG-demo/
├── main.py                  # FastAPI 入口
├── 需求文档.md               # 原始产品需求(中文)
├── app/
│   ├── core/                # 配置 + LLM + Embedding + Milvus 客户端
│   ├── rag/                 # RAG 五段流水线
│   └── api/                 # FastAPI 路由
├── data/
│   └── sample_kb.md         # 示例知识库
├── static/
│   ├── index.html           # Web 界面
│   └── cache/               # 运行时缓存(被 gitignore)
├── uploads/                 # 用户上传的文档(被 gitignore)
└── .env                     # 本地配置(被 gitignore,不进仓库)
```

---

## 7. License

MIT(欢迎 fork / 二次开发)
