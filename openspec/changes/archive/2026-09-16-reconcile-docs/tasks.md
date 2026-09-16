# 任务清单:文档对齐

## 1. 重写 `CLAUDE.md`

- [x] 1.1 改写 §0 "项目一句话":明确"5 段流水线" + "Claude 工作的唯一真相源" + OpenSpec 指针
- [x] 1.2 §1 "常用命令"补全 `/upload/files`、`/upload/dir`、`GET /upload/files` 三个接口的 curl 示例
- [x] 1.3 §2 "代码架构"补 retriever 的 known-coupling 警告(指向 `use-processed-query-in-retriever`)
- [x] 1.4 §3 "关键设计取舍"新增"MILVUS_DB 未生效"段(指向 `fix-milvus-db-name-ignored`)
- [x] 1.5 §4 ".env 必填项"加 `MILVUS_DB` 标注"当前未生效",MinerU 开关段指向 `wire-mineru-pipeline`
- [x] 1.6 §5 "调试清单"加"数据'看起来入库了'但查的是别库"条目
- [x] 1.7 新增 §6 "变更规范 (OpenSpec)" — 解释 `openspec/` 目录结构和 4 个动作
- [x] 1.8 新增 §7 "指针" — 列出 README / docs / 各 spec 的入口

## 2. 精简 `README.md`

- [x] 2.1 移除重复的架构表格(改指向 CLAUDE.md)
- [x] 2.2 移除重复的阈值 / 接口细节(改指向 CLAUDE.md)
- [x] 2.3 补"目录结构"段,把 `openspec/` 和 `docs/` 标出来
- [x] 2.4 补"贡献流程"段指向 `openspec/AGENTS.md`

## 3. 归档 `需求文档.md`

- [x] 3.1 `mkdir -p docs`
- [x] 3.2 `git mv 需求文档.md docs/requirements-archive.md`(注意文件原本是 untracked,实际 `mv` 等价)
- [x] 3.3 在 `docs/requirements-archive.md` 顶部加 HTML 注释块,说明已归档并指向 CLAUDE.md

## 4. 引导 `openspec/`

- [x] 4.1 写 `openspec/AGENTS.md`(Claude 在此目录工作的指令)
- [x] 4.2 写 `openspec/project.md`(项目上下文 + 已知问题 + 产品语言)
- [x] 4.3 写 6 份能力规格:`specs/{query-understanding,hybrid-retrieval,reranking,answer-generation,document-indexing,api-surface}/spec.md`
- [x] 4.4 写 3 个未实施 change:`changes/{wire-mineru-pipeline,fix-milvus-db-name-ignored,use-processed-query-in-retriever}/`
- [x] 4.5 reconcile-docs 自己的 `.openspec.yaml` + `proposal.md` + `tasks.md`(本文件)+ `design.md`

## 验证

- [x] V.1 `git status --short` 显示预期的 6 类变更(详见 `design.md` 的 "Expected diff surface")
- [x] V.2 三份文档对"流水线段数 / 阈值 / 上传路径"口径一致 — 人工逐节对照
- [x] V.3 `docs/requirements-archive.md` 顶部有 HTML 注释"archived 2026-09-16"
- [x] V.4 `openspec/specs/` 下 6 个目录,每个含 `spec.md`
- [x] V.5 `openspec/changes/` 下 4 个目录,每个含 `proposal.md` + `tasks.md` + `design.md` + `.openspec.yaml`
- [x] V.6 `openspec/changes/wire-mineru-pipeline/specs/document-indexing/spec.md` 存在且使用 `## ADDED Requirements` 章节头