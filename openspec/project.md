# project.md — Agentic-RAG-demo 项目上下文

## 目的

一个端到端的、可演示的模块化 RAG 流水线。**重点是"模块边界清晰 + 每段可替换可观测"**,不是性能极致,不是产品化打磨。

## 技术栈

| 层 | 选型 |
|---|---|
| LLM | MiniMax-M3(OpenAI 兼容协议) |
| Embedding | MiniMax `embo-01`(私有协议,**与 OpenAI 不兼容**) |
| 向量库 | Milvus standalone(Docker) |
| 重排 | BAAI/bge-reranker-v2-m3(CrossEncoder,本地 MPS/CPU) |
| 索引框架 | llama-index(`VectorStoreIndex` + `QueryFusionRetriever`) |
| Web 框架 | FastAPI + Uvicorn |
| 文档加载 | `UnstructuredReader`(llama-index 自带)— Markdown 直读 |
| 文档切分 | `MarkdownNodeParser` 按标题层级 |
| 运行时 | Python ≥ 3.11,conda 环境 `rag`,macOS 支持 MPS |

## 架构

5 段流水线,严格串行:

```
pre_query → retriever → post → generator
            ↑pipeline 编排
```

详情见 [CLAUDE.md §2](../CLAUDE.md#2-代码架构与模块职责) 和 `specs/` 下各能力规格。

## 仓库约定

- **没有 `requirements.txt`**:依赖按需 pip install,见 [CLAUDE.md §1](../CLAUDE.md#1-常用命令)
- **没有测试套件**:本仓库是 demo,不做 CI
- **没有 `.env.example`**:敏感配置直接抄 [CLAUDE.md §4](../CLAUDE.md#4-env-必填项)
- **没有 CI**:不做 lint / format check
- **`.env` / `uploads/` / `static/cache/` 全部 gitignore**
- **OpenSpec**:变更提案走 `openspec/changes/<name>/`,详见 [openspec/AGENTS.md](./AGENTS.md)

## 已知问题(均已记录到 changes/)

- `MILVUS_DB` 配置项实际未生效 — MilvusVectorStore 写到 default DB → `changes/fix-milvus-db-name-ignored/`
- 检索时把 `processed.original` 喂给 fuser,`rewritten` / `expanded` 仅作兜底 → `changes/use-processed-query-in-retriever/`
- MinerU 开关已就位但 loader/upload 未接通 → `changes/wire-mineru-pipeline/`

## 产品语言

本仓库所有 OpenSpec proposal / spec 都用**用户可观测的产品行为语言**,不用实现细节:
- ✅ "When the user uploads a PDF, the system SHALL extract text and ingest it within 60s"
- ❌ "When `ingest()` is called with a PDF path, the function calls `subprocess.run(['mineru', ...])`"