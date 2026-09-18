# Proposal

## Why

`upgrade-mineru-cli` 把 CLI 调用语法切到新版,但选了 `--tier flash`(纯文本占位符,不解析图片),导致管理页"查看转换结果"弹层里图片显示成 `![Image block](doc:...)` 占位符。本机 M4 16GB 已下载完整 pipeline 模型集(2.4GB,Layout/MFR/OCR/TabCls/TabRec),足以跑 **basic tier + pipeline backend 纯 CPU**(精度 86.47,满足 RAG 检索 + 人工核对),无须额外下载模型。图片、版面、表格、公式都能正确解析落盘到 markdown。

## What Changes

- `mineru config set parse_server.local.mode managed` 启用本地 parse-server,`mineru config set parse_server.local.managed_tier basic` 锁定到 basic tier
- `mineru server start` 后台常驻(parse-server 在 server 进程内运行)
- `app/rag/loader.py::convert_to_markdown` 把 `--tier flash` 改为 `--tier basic`(其余 CLI 语法不变)
- 模型路径不变(`~/.mineru/models/...` 由 mineru-kit 自动从 `models-dir` 在 `~/mineru.json` 推断,如缺符号链接补齐)
- 重新转换已入库的 PDF(`converted/尚硅谷-01-LangChain概述.pdf.md` 被新版 basic tier 覆写)

## Capabilities

### Modified Capabilities
- `document-loading`:新增 Scenario "basic tier 启用后图片提取到 markdown" 与 "已转换产物被重新解析覆写";`MINERU_ENABLED` 开关语义、产物路径 `converted/<原文件名>.md` 不变

## Impact

- `app/rag/loader.py`:仅 `--tier flash` → `--tier basic`(一行)
- 系统层:`mineru server` 重启(`mode=managed` 后启动行为不同),耗时多几秒
- 性能:basic + pipeline 纯 CPU 跑 25 页 PDF 预计 30-90 秒(flash 0.3 秒)
- 不影响:其他路由、Milvus schema、检索/重排
- 不下:本机已下完 pipeline 模型集,无需新下载

## Notes

- 之前 `upgrade-mineru-cli` 设计的 flash tier 现在被本变更覆盖(tier=basic);但 `document-loading` 能力 path 不变(同一能力,只是 tier 选项升级)
- 如未来想用 `standard`/`advanced` 或 `vlm-engine`,再开新变更(需要 VLM GGUF 权重下载)
- 远程 `mineru.net` 路线不采纳(本地已可)