# Agentic-RAG-demo

端到端的模块化 RAG 流水线。把"基于自有资料回答问题"拆成 **查询预处理 → 向量召回 → 重排 → 答案生成** 五段,每段独立、可替换、可观测。

- **LLM**:`MiniMax-M3`(OpenAI 兼容协议)
- **Embedding**:`embo-01`(MiniMax,**协议与 OpenAI 不兼容**,已封装适配器)
- **向量库**:Milvus(standalone,Docker 部署)
- **重排**:`BAAI/bge-reranker-v2-m3`(本地 MPS/CPU)
- **运行时**:Python ≥ 3.11,FastAPI

> **给 Claude Code / AI 助手的指令**:看 [CLAUDE.md](./CLAUDE.md)。
> **历史产品需求**:归档在 [docs/requirements-archive.md](./docs/requirements-archive.md),仅供考古。
> **架构细节 / 模块边界 / 设计取舍 / 调试清单**:都在 CLAUDE.md,本 README 不重复。

---

## 1. 快速开始

### 1.1 准备环境

```bash
conda create -n rag python=3.11 -y
conda activate rag

# 装核心依赖(项目不提供 requirements.txt)
pip install fastapi uvicorn python-dotenv pymilvus \
            llama-index llama-index-vector-stores-milvus llama-index-readers-file \
            sentence-transformers torch
```

### 1.2 启动 Milvus(必须)

```bash
docker run -d --name milvus-standalone \
  -p 19530:19530 -p 9091:9091 \
  -v ~/milvus-data:/var/lib/milvus \
  milvusdb/milvus:v2.4-latest
curl http://localhost:9091/healthz   # → OK
```

### 1.3 写 `.env`

根目录建 `.env`(被 `.gitignore` 排除),从 CLAUDE.md §4 复制。**`MINIMAX_GROUP_ID` 是 embedding 必填**(MiniMax 私有协议要求,丢 URL query)。

### 1.4 启动 + 试用

```bash
mkdir -p uploads static/cache
uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# 入库
curl -F "file=@./data/sample_kb.md" http://127.0.0.1:8000/upload/files

# 提问
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"什么是 embedding?","history":[]}'
```

Web UI:http://127.0.0.1:8000/ · 接口文档:http://127.0.0.1:8000/docs

---

## 2. 目录结构

```
Agentic-RAG-demo/
├── main.py                  FastAPI 入口
├── CLAUDE.md                Claude 工作唯一真相源
├── README.md                你正在看的
├── docs/
│   ├── requirements-archive.md   历史产品需求(已归档)
│   ├── specs/               已部署能力规格
│   └── changes/             进行中的变更提案
├── app/
│   ├── core/                配置 + LLM + Embedding + Milvus 客户端
│   ├── rag/                 五段流水线
│   └── api/                 FastAPI 路由
├── data/sample_kb.md        示例知识库
├── static/                  Web UI + 缓存
└── uploads/                 用户上传的文档
```

---

## 3. 贡献流程

任何非琐碎改动(改 app/ 下任何文件、加新接口、调整流水线结构)都从 OpenSpec 开始:

1. 读 `docs/changes/` 下相关提案,看是否已有
2. 没有则建一个新 change:`docs/changes/<name>/{proposal,tasks}.md`
3. 改完代码,在 `docs/changes/<name>/specs/<capability>/spec.md` 写 future-state 规格(若能力有变)

详见 [CLAUDE.md](./CLAUDE.md)。

---

## 4. License

MIT(欢迎 fork / 二次开发)
