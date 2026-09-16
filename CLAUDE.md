# CLAUDE.md

> 给 Claude Code 的项目指令。**项目特定上下文**放这里;**行为规则**放 `.claude/rules/core-rules.md`(必读);**架构契约**放 `openspec/specs/`。
> GitHub 访客看 [README.md](./README.md);历史产品需求归档在 [docs/requirements-archive.md](./docs/requirements-archive.md)。

## Project Overview

- 端到端模块化 RAG 流水线。用户问题 → 查询预处理 → 向量召回 → 后处理(过滤 + 重排) → 答案生成。**5 段**,每段独立、可替换、可观测。
- LLM: MiniMax-M3(OpenAI 兼容)·Embedding: MiniMax `embo-01`(私有协议)·向量库: Milvus standalone(Docker)·重排: BAAI/bge-reranker-v2-m3(本地 MPS/CPU)
- 索引框架: llama-index ·Web 框架: FastAPI ·运行时: Python ≥ 3.11,conda 环境 `rag`
- 入口: `main.py`(`uvicorn main:app --host 127.0.0.1 --port 8000 --reload`)

## Build, Test & Verify

```bash
# 装核心依赖(项目不提供 requirements.txt)
conda activate rag
pip install fastapi uvicorn python-dotenv pymilvus \
            llama-index llama-index-vector-stores-milvus llama-index-readers-file \
            sentence-transformers torch

# 起 Milvus(必须)
docker run -d --name milvus-standalone \
  -p 19530:19530 -p 9091:9091 \
  -v ~/milvus-data:/var/lib/milvus \
  milvusdb/milvus:v2.4-latest
curl http://localhost:9091/healthz   # → OK

# 起服务 + 冒烟测试
mkdir -p uploads static/cache
uvicorn main:app --host 127.0.0.1 --port 8000 --reload

curl -F "file=@./data/sample_kb.md" http://127.0.0.1:8000/upload/files
curl -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" \
  -d '{"query":"什么是 embedding?","history":[]}'

# BGE 重排模型首启会下载 2.2GB(国内镜像)
export HF_ENDPOINT=https://hf-mirror.com

# 验证 OpenSpec 改动
openspec validate --changes      # 全部 active change
openspec validate <change-name>  # 单个
openspec list                    # 当前 proposals
```

**改完之后**:跑对应 `openspec/changes/<name>/tasks.md` 里的 Verification 段(每条 change 自带)。

## Code Style(只列偏离默认的)

- 每个 `app/` 文件**单一职责**,文件顶部 docstring 第一行就是它干什么
- 中文 docstring + 英文代码标识符(README / CLAUDE.md / 用户可见消息一律中文)
- 不引入新 Python 包前先看 CLAUDE.md §Build 段;引入了就在 openspec change 里写明
- 改了 `.env` 字段必须同步本文件 §Build 与 `.claude/rules/core-rules.md`

## Architecture(只看路径,契约查 `openspec/specs/`)

```
main.py                  FastAPI 入口
app/core/                配置 + LLM + Embedding + Milvus 客户端
app/rag/                 五段流水线
app/api/                 FastAPI 路由
openspec/specs/          已部署能力契约(6 份)
openspec/changes/        进行中的变更提案(3 份待实施)
openspec/changes/archive/ 已归档的变更(完整审计链)
docs/                    历史归档
data/                    示例知识库
uploads/                 用户上传(被 gitignore)
static/cache/            运行时缓存(被 gitignore)
converted/               MinerU 输出目录(被 gitignore)
```

## When to read more

| 场景 | 读 |
|---|---|
| 改 `app/` 下任何模块 | `openspec/changes/` 下相关 proposal + `openspec/specs/<能力>/spec.md` |
| 改 API 契约 | `openspec/specs/api-surface/spec.md` |
| 调试召回 / 重排 / 生成 | `openspec/specs/{hybrid-retrieval,reranking,answer-generation}/spec.md` |
| 改索引 / 切分 / 加载 | `openspec/specs/document-indexing/spec.md` |
| 改查询预处理 | `openspec/specs/query-understanding/spec.md` |
| 行为约束 / 硬规则 | `.claude/rules/core-rules.md` |
| 启动报环境变量缺失 / Milvus 连不上 / 召回 0 / MPS 报错 | 本文件 §Debug Cookbook(见下) |

## Debug Cookbook(症状 → 命令)

| 症状 | 跑 |
|---|---|
| 启动报 `环境变量 XXX 未配置` | `cat .env` 看缺哪个字段(必填清单见 README) |
| Milvus `14 UNAVAILABLE` | `docker ps \| grep milvus`;`MILVUS_URI=http://localhost:19530` |
| 首启几十秒慢 | BGE 模型首次下载 2.2GB;`export HF_ENDPOINT=https://hf-mirror.com` |
| PDF 入库召回 0 | `grep -n '_get_text_embedding\|_get_query_embedding' app/rag/indexer.py` — 必须是 db 模式 |
| 数据"看起来入了"但召回是别库 | `MILVUS_DB` 当前未生效,见 `openspec/changes/fix-milvus-db-name-ignored/` |
| Apple Silicon `sentence-transformers` 报错 | `pip install torch` 装 MPS 版本;`post.py` 已自动 `device="mps"` |
| `openspec validate` 失败 | `openspec validate <change> --json` 看具体错误 |

## 不在本仓库

- 不创建 `.claude/settings.json` hooks(改所有会话行为,风险/收益不匹配)
- 不创建 `CLAUDE.local.md` 占位(那是个人偏好,不该预设)
- 不为本仓库扩 `memory/` 子系统(YAGNI,本项目无跨 worktree 需求)
- 不写测试套件 / CI / lint(本项目是 demo)
