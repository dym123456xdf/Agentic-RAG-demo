# CLAUDE.md

5 段模块化 RAG 流水线(查询预处理 → 向量召回 → 后处理 → 答案生成)。
入口 `main.py`;Python ≥ 3.11,conda 环境 `rag`。
行为规则: [`.claude/rules/core-rules.md`](./.claude/rules/core-rules.md)(必读)。
架构契约: [`openspec/specs/`](./openspec/specs/)。变更: [`openspec/changes/`](./openspec/changes/)。

## Verify

改完代码后跑 `openspec validate --changes`。
HF 重排首启:`export HF_ENDPOINT=https://hf-mirror.com`。

## Debug

- PDF 召回 0:`grep -n '_get_text_embedding' app/rag/indexer.py` 必须用 `db` 模式
- `MILVUS_DB` 不生效:见 `openspec/changes/fix-milvus-db-name-ignored/`
- MPS 报错:`pip install torch` 装 MPS
