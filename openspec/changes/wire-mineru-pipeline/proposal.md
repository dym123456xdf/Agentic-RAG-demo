# Wire MinerU into the Loader Pipeline

## Why

PDF / DOCX / PPTX 当前走 `UnstructuredReader`,在 Apple Silicon M 系列芯片上召回质量明显劣于 MinerU(M4 16 GB 友好的本地 PDF 解析工具)对中文 / 表格 / 扫描件的还原。

`app/core/config.py` 已经把 4 个 MinerU 开关就位(`MINERU_ENABLED` / `MINERU_BIN` / `MINERU_OUTDIR` / `MINERU_TIMEOUT_S`),`Config.ensure_dirs()` 也会建 `converted/` 目录,但 `app/rag/loader.py` 和 `app/api/upload.py` **完全没用上**任何 `MINERU_*` 字段 — `MINERU_ENABLED=true` 设了跟没设一样,这是个"开关摆在那里没人拨"的悬空状态。

如果不接通,这 4 个开关会持续误导新人("看起来有 MinerU 支持,试试看?")。

## What Changes

在 `loader.py` 里加一条分支:当 `Config.MINERU_ENABLED` 为 True 且后缀是 `.pdf/.docx/.pptx` 时,**先**把文件丢给 MinerU 解析成 markdown(落到 `MINERU_OUTDIR/`),**再**用 markdown 直读路径进入 `MarkdownNodeParser`。当开关关闭或文件是 `.md/.markdown/.txt` 时,行为不变(fallback 到现有 UnstructuredReader 或直读)。

**影响范围**:
- 修改:`app/rag/loader.py`(新增 `_load_via_mineru(path)` 函数 + `_load_one` 分支)
- 修改:`app/api/upload.py`(在 list_files / clear_files 等端点的注释里说明 `MINERU_OUTDIR` 是缓存区,误删会强制重新解析)
- 修改:`CLAUDE.md`(更新"已知中间态"段,从"开关已加 loader 未接通"改成"按 wire-mineru-pipeline 走")— 注意:**仅在 change archive 时才改 CLAUDE.md**,实施中 CLAUDE.md 仍指此处
- **不动**:`app/core/config.py`(4 个开关已经就位)、`app/rag/{splitter,indexer}.py`(markdown 路径完全复用现有逻辑)

**新增能力**(记入 `specs/document-indexing/spec.md` 的 ADDED Requirements):
- 当 MinerU 启用时,PDF / DOCX / PPTX 必须经 MinerU 解析后才入库
- 同名文件二次上传必须复用 `MINERU_OUTDIR/` 下的缓存,不重新调 MinerU
- MinerU 解析失败必须抛出明确错误(包含可读的 stdout / stderr 摘要),不允许静默 fallback 到 UnstructuredReader(避免召回质量无提示劣化)
- MinerU 输出目录里的图片不入库(只入 markdown 文本),但保留在 `MINERU_OUTDIR` 下供前端引用

## Non-Goals

- **不重写** UnstructuredReader 路径(MinerU 是可选升级,不是替代)
- **不支持**扫描件 OCR(MinerU 自身能力决定,本系统不集成 OCR 后处理)
- **不实现** MinerU 解析进度上报 / 异步队列(单 PDF 同步,靠 `MINERU_TIMEOUT_S` 防卡死)
- **不修改** MilvusVectorStore 的 db_name 问题(那是 `fix-milvus-db-name-ignored` 的事,本 change 不动 `app/core/milvus_client.py`)

## Out of Scope

- 选择 MinerU vs Marker vs Unstructured vs 其他 PDF 解析库的取舍 — 假设 MinerU 已是决策
- 跨 PDF 引用 / 目录抽取 / 章节合并 — 都不做
- 解析后清洗(去水印 / 去页眉页脚)— 留给上游提供更干净的原 PDF

## Success Criteria

1. `MINERU_ENABLED=true` + `.env` 配好 `MINERU_BIN` → 上传 PDF 后能在 `MINERU_OUTDIR/<name>.md` 看到 markdown 输出
2. 同名 PDF 二次上传 → 不产生新的 minerU 调用,直接复用缓存
3. `MINERU_ENABLED=false`(默认)→ 行为与本次 change 之前完全一致(回归测试:已上传的 sample_kb.md 仍能正常检索)
4. minerU 二进制缺失或解析超时 → 抛 `RuntimeError` 而不是降级