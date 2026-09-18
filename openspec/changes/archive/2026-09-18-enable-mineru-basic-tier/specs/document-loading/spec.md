# Spec Delta

## Purpose

将 `document-loading` 能力的默认 MinerU tier 从 `flash`(纯文本占位符)升级到 `basic`(含图片/版面/表格/公式的完整解析)。本机 M4 16GB 已下完整 pipeline 模型集,basic + pipeline 纯 CPU 即可,无需新下载模型。

## MODIFIED Requirements

### Requirement: 新版 MinerU CLI 调用契约

系统 SHALL 使用新版 MinerU CLI 语法调用:`mineru parse <path> --tier basic --wait <secs> --pages 1-1000 --limit 200000`,markdown 文本写到 stdout;旧版 `[bin, "-p", path, "-o", dir]` 调用语法不再使用。

#### Scenario: 旧版调用已下线
- **WHEN** 任何代码路径触发 MinerU 转换
- **THEN** 子进程命令行包含 `parse` 子命令,不含旧版 `-p path -o dir` 形态

#### Scenario: 显式 tier
- **WHEN** 调用 MinerU 转换 PDF/DOCX/PPTX
- **THEN** 命令行必须包含 `--tier basic`,产物含图片/版面/表格/公式的完整解析;`flash` 为纯文本提取(图片只出 `![Image block](doc:...)` 占位符),不再采用

#### Scenario: 表格与公式保留
- **WHEN** 上传一份含表格或 LaTeX 公式的 PDF
- **THEN** 转换产物保留表格 markdown 结构或 `$...$` / `$$...$$` 公式,非空文本

## ADDED Requirements

### Requirement: parse-server 本地启用

系统 SHALL 在本地启动 MinerU parse-server(`mode=managed`,`managed_tier=basic`),由 `mineru server start` 拉起并常驻;调用方不感知具体 server 进程。

#### Scenario: parse-server 启动后可用
- **WHEN** `mineru server status` 报告 parse-server running 且 tier=basic
- **THEN** `mineru parse --tier basic` 调用成功,不被 "Local parse-server is disabled" 拒绝

#### Scenario: parse-server 失败
- **WHEN** parse-server 未起就调 `mineru parse --tier basic`
- **THEN** 报 "Local parse-server is disabled. Use --tier flash or --remote.",调用方应 fail-fast
