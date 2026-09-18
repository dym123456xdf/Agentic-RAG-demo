# Proposal

## Why

`app/rag/loader.py::convert_to_markdown` 仍按 MinerU 旧版 CLI 语法调用 `[bin, "-p", path, "-o", out_dir]`,而 `MINERU_BIN` 已经升级到新版 CLI(`mineru --help` 显示顶层是子命令式,`-p` 不再是输入文件而是页码范围)。结果是所有 PDF/DOCX/PPTX 上传 500(`No such option: -p`),整个 MinerU 通道在生产环境失效,但 UnstructuredReader 兜底仍能跑 — 这条死路必须修。

## What Changes

- `app/rag/loader.py::convert_to_markdown` 调用方式改为新版 CLI:`mineru parse <path> --tier flash --wait <secs> --pages 1-1000 --limit 200000`,markdown 写到 stdout
- 新版 CLI 强制要求显式 `--tier`(默认 tier 依赖 local parse-server,而 parse-server 默认 disabled),只能用 `--tier flash`(纯文本提取)或 `--remote`
- 不再通过 `-o` 目录模式落盘(目录会触发 "Is a directory"),改为落盘前由 `proc.stdout` 取回文本写到 `converted/<原文件名>.md`
- 行为不变:`MINERU_ENABLED=false` 时仍走 UnstructuredReader 兜底;产物已存在直接复用;失败(非零退出 / 超时 / 空 stdout)抛 RuntimeError

## Capabilities

### New Capabilities
- `document-loading`:PDF/DOCX/PPTX 经 MinerU 通道转 Markdown 入库的端到端契约,覆盖新版 CLI 调用、产物落盘路径、错误语义、`MINERU_ENABLED` 开关

### Modified Capabilities

(项目当前无 main specs,均为新能力)

## Impact

- `app/rag/loader.py`:仅改 `convert_to_markdown` 内部;外部签名、产物路径(`converted/<原文件名>.md`)、`MINERU_ENABLED` 开关语义不变
- 运维:`mineru server start` 必须先跑(原 CLI 是直接调二进制,新版是 client + 本地服务架构)。文档里要写
- 不影响:其他路由、Milvus schema、检索/重排逻辑
- 兼容性:无 BREAKING — 旧 MinerU 客户端或旧版二进制仍兼容同一契约,但需要 server 进程

## Notes(实施期已发现但本变更不覆盖)
- 这次修复同时改了一条:`.env` `LLM_PROVIDER=glm` → `minimax`(CLAUDE.md 默认),仅切换回基线
- 服务监听端口因 8000 被 Docker Desktop 反向代理占用,改用 8011(无代码变更,只是启动参数)