# CLAUDE.md

5 段模块化 RAG 流水线:查询预处理 → 向量召回 → 后处理 → 答案生成。
入口 `main.py`,Python ≥ 3.11,conda 环境 `rag`。

## 必读

- 行为规则 — [`.claude/rules/core-rules.md`](./.claude/rules/core-rules.md)
- 架构契约 — [`openspec/specs/`](./openspec/specs/)
- 变更规范 — [`openspec/changes/`](./openspec/changes/)

## Build

```bash
# 起 Milvus(必须)
docker run -d --name milvus-standalone \
  -p 19530:19530 -p 9091:9091 \
  -v ~/milvus-data:/var/lib/milvus \
  milvusdb/milvus:v2.4-latest
curl http://localhost:9091/healthz   # → OK
```

## Test & Verify

```bash
# 起服务
uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# 冒烟测试
curl -F "file=@./data/sample_kb.md" http://127.0.0.1:8000/upload/files
curl -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" \
  -d '{"query":"什么是 embedding?","history":[]}'

# BGE 重排首启 2.2 GB 国内镜像
export HF_ENDPOINT=https://hf-mirror.com

# 改完代码后必跑
openspec validate --changes
```

## Debug

| 症状 | 命令 |
|---|---|
| PDF 召回 0 | `grep -n '_get_text_embedding' app/rag/indexer.py` 必须用 `db` 模式 |
| `MILVUS_DB` 不生效 | 见 `openspec/changes/fix-milvus-db-name-ignored/` |
| Apple Silicon 报错 | `pip install torch` 装 MPS,`post.py` 已自动 `device="mps"` |
| `openspec validate` 失败 | `openspec validate <change> --json` |
