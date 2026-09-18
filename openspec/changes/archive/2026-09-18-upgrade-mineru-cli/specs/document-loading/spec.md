# Spec Delta

## Purpose

覆盖 PDF / DOCX / PPTX 经 MinerU 通道转 Markdown 入库的端到端契约:CLI 调用语法、产物落盘、错误语义、`MINERU_ENABLED` 开关行为。

## ADDED Requirements

### Requirement: 新版 MinerU CLI 调用契约

系统 SHALL 使用新版 MinerU CLI 语法调用:`mineru parse <path> --tier flash --wait <secs> --pages 1-1000 --limit 200000`,markdown 文本写到 stdout;旧版 `[bin, "-p", path, "-o", dir]` 调用语法不再使用。

#### Scenario: 旧版调用已下线
- **WHEN** 任何代码路径触发 MinerU 转换
- **THEN** 子进程命令行包含 `parse` 子命令,不含旧版 `-p path -o dir` 形态

#### Scenario: 显式 tier
- **WHEN** 调用 MinerU 转换 PDF/DOCX/PPTX
- **THEN** 命令行必须包含 `--tier flash`(`basic/standard/advanced` 依赖未启用的 local parse-server,会报错;`flash` 是纯文本提取,无需 parse-server)

### Requirement: 一次拉全部页

系统 SHALL 通过 `--pages 1-1000 --limit 200000` 一次拉完文档全部内容;后续不再循环分页。

#### Scenario: 25 页 PDF 一次性完成
- **WHEN** 提交一份 25 页 PDF 转换
- **THEN** 单次调用 stdout 包含全部 25 页 markdown 文本,响应中 `next_request` 为 null

### Requirement: 产物落盘到 `converted/<原文件名>.md`

系统 SHALL 将 MinerU stdout 的 markdown 文本写到 `Config.MINERU_OUTDIR/<path.name>.md`;产物已存在直接复用,不重复转换。

#### Scenario: 产物已存在时跳过转换
- **WHEN** `converted/<原文件名>.md` 已存在
- **THEN** 不调 mineru,直接返回该路径

#### Scenario: 落盘位置
- **WHEN** 调用方传一个 PDF 文件 `xxx.pdf`
- **THEN** 转换产物写到 `MINERU_OUTDIR/xxx.pdf.md`(保留原后缀避免同名冲突,与旧契约一致)

### Requirement: 错误语义

MinerU 转换失败 SHALL 抛 RuntimeError 且带可定位信息(原文件名 + stderr 摘要),不静默回退到 UnstructuredReader;调用方决定是否 fallback。

#### Scenario: 非零退出
- **WHEN** MinerU 退出码非零
- **THEN** 抛 RuntimeError,信息含 `returncode=<N>`、`<原文件名>`、最近 500 字符 stderr

#### Scenario: 超时
- **WHEN** 转换超过 `MINERU_TIMEOUT_S`
- **THEN** 抛 RuntimeError,信息含超时上限与文件名

#### Scenario: 空 stdout
- **WHEN** MinerU 退出 0 但 stdout 为空
- **THEN** 抛 RuntimeError,信息含文件名与最近 500 字符 stderr

### Requirement: `MINERU_ENABLED` 开关

系统 SHALL 提供 `MINERU_ENABLED` 开关:为 true 时 PDF/DOCX/PPTX 走 MinerU 通道;为 false 时 fallback 到 UnstructuredReader(行为与历史一致)。

#### Scenario: 开关关闭
- **WHEN** `MINERU_ENABLED=false` 且上传 PDF
- **THEN** 不调 mineru,走 UnstructuredReader,无产物写入 `converted/`

#### Scenario: 开关开启
- **WHEN** `MINERU_ENABLED=true` 且上传 PDF
- **THEN** 走新版 MinerU 通道,产物写入 `converted/`