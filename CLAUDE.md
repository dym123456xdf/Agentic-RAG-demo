# CLAUDE.md

> 项目特定上下文。行为规则看 [`.claude/rules/core-rules.md`](./.claude/rules/core-rules.md)(必读);架构契约看 [`openspec/specs/`](./openspec/specs/);访客看 [README.md](./README.md);历史需求看 [docs/requirements-archive.md](./docs/requirements-archive.md)。

## Project

端到端模块化 RAG 流水线,5 段:查询预处理 → 向量召回 → 后处理(过滤 + 重排) → 答案生成。
入口 `main.py`。Python ≥ 3.11,conda 环境 `rag`。

## Build, Test & Verify

```bash
# 起 Milvus(必须)
docker run -d --name milvus-standalone \
  -p 19530:19530 -p 9091:9091 \
  -v ~/milvus-data:/var/lib/milvus \
  milvusdb/milvus:v2.4-latest
curl http://localhost:9091/healthz   # → OK

# 起服务
uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# 冒烟测试
curl -F "file=@./data/sample_kb.md" http://127.0.0.1:8000/upload/files
curl -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" \
  -d '{"query":"什么是 embedding?","history":[]}'

# BGE 重排模型首启会下 2.2 GB(国内镜像)
export HF_ENDPOINT=https://hf-mirror.com

# 验证 OpenSpec 改动
openspec validate --changes
openspec list
```

## When to read more

| 场景 | 读 |
|---|---|
| 改 `app/` 下任何代码 | `openspec/changes/` 下相关 proposal + `openspec/specs/<能力>/spec.md` |
| 调试 / 理解行为 | [`.claude/rules/core-rules.md`](./.claude/rules/core-rules.md)(硬约束集中地) |

## Debug Cookbook

| 症状 | 跑 |
|---|---|
| PDF 入库后召回 0 | `grep -n '_get_text_embedding\|_get_query_embedding' app/rag/indexer.py` — 必须是 `db` 模式 |
| 数据"看起来入了"但召回是别库 | `MILVUS_DB` 当前未生效,见 `openspec/changes/fix-milvus-db-name-ignored/` |
| Apple Silicon `sentence-transformers` 报错 | `pip install torch` 装 MPS;`post.py` 已自动 `device="mps"` |
| `openspec validate` 失败 | `openspec validate <change> --json` 看具体错误 |
