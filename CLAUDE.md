# CLAUDE.md

5 段模块化 RAG 流水线:查询预处理 → 向量召回 → 后处理 → 答案生成。
入口 `main.py`,Python ≥ 3.11,conda 环境 `rag`。

## 必读

- 行为规则 — [`.claude/rules/core-rules.md`](./.claude/rules/core-rules.md)
