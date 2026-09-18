# Design

## Context

参见 proposal.md - Why。本次变更前现状:
- `app/rag/loader.py::convert_to_markdown` 用 `[MINERU_BIN, "-p", path, "-o", out_dir]` 调用,新版 MinerU CLI 顶层是子命令式,`-p` 已是页码范围参数
- 新版 CLI 输出形式:markdown 写到 stdout,不再落盘 `-o` 目录
- 新版 CLI 默认 tier 要求 local parse-server,而 parse-server 默认 disabled(`Local parse-server is disabled. Use --tier flash or --remote.`),只能用 `--tier flash`(纯文本)或 `--remote`(走远程)
- 新版 MinerU 是 client + 本地服务架构,需先 `mineru server start`
- 之前 PDF 上传一直挂 500 是因为没修 CLI,不是 server 没起(修复时 server 是停的也能下到错误,但新版要起 server 才能 `mineru parse` 真正跑通)

## Goals / Non-Goals

**Goals:**
- 让新版 MinerU CLI 在不引入新依赖的前提下完成 PDF/DOCX/PPTX → Markdown 转换
- 保持旧契约:`MINERU_ENABLED` 开关语义、产物路径 `converted/<原文件名>.md`、失败抛 RuntimeError 不静默 fallback、产物已存在复用
- 一次拉完全部页(避免循环分页拉取的复杂度,经验证 25 页 PDF 单次调用 0.3 秒命中 cache)

**Non-Goals:**
- 不启用 local parse-server(basic/standard/advanced tier)— 留给后续,如果需要 OCR / 版面分析再开
- 不接远程 MinerU(`--remote`)— 网络与凭据治理不在本变更范围
- 不改 `MINERU_ENABLED=false` 时的 UnstructuredReader 路径
- 不动 mineru server 的启动/停止脚本 — 那是 ops 文档职责,本变更只把 loader.py 改对

## Decisions

### D1. tier=flash(纯文本提取)
不引入 OCR/版面分析,够 RAG 检索用;且不依赖 parse-server,部署最简单。备选:`--remote`(要凭据 + 网络)、`basic/standard/advanced`(要启 parse-server + 模型权重,部署重)。

### D2. 一次拉全部页:`--pages 1-1000 --limit 200000`
经验证 25 页 PDF 单次返回 19.6KB markdown,`next_request=null`,`truncated=false`,耗时 0.3 秒(cache 命中)。`1-1000` 是页数上限,远超实际文档;`200000` 字符上限约 200KB,也远超典型 PDF 文本量。备选:循环分页 `--pages N-M` + `--after`,代码复杂度高但支持任意长度 PDF;本变更不引。

### D3. 落盘路径与旧契约一致:`MINERU_OUTDIR/<path.name>.md`
保留原文件后缀(`.pdf` / `.docx` / `.pptx`)避免同名冲突 — 这是 `converted_md_path()` 既定行为。备选:`<stem>.md`(去后缀),冲突风险;不在意。

### D4. 不依赖 mineru server 启动检查
loader.py 不强校验 `mineru server status`,让 subprocess 失败抛错;避免 loader 引入新状态机。运维侧在启动文档里写明要先 `mineru server start`。

### D5. 错误信息保留 stderr 摘要(最近 500 字符)
与旧实现一致 — 既有 `upload.py` 已 `RuntimeError` 透传给前端,前端 toast 已经能展示。新版 stderr 通常更长(`╭─ Error ─╮` 富文本框),截 500 字符够定位。

## Risks / Trade-offs

- [PDF 含图片 / 扫描件] → `flash` 不做 OCR,纯文本抽取,扫描件 PDF 出来是空文本;Mitigation:`flash` 已能覆盖业务场景(教程、博客、技术文档),扫描件若出现再升级 tier
- [超大 PDF(>500 页)] → `--pages 1-1000` 截到 1000 页,可能截断;Mitigation:RAG 通常文档不长,后续如有超长文档可加分页循环
- [新版 mineru 服务宕] → 单次调用失败抛 RuntimeError,前端 toast 报错;Mitigation:运维侧 `mineru server status` 自检
- [cache 占用磁盘] → `mineru server` 会缓存所有解析过的文档,`~/` 目录;Mitigation:在 ops 文档提一句定期 `mineru server cleanup`

## Migration Plan

1. 应用本次代码变更(`convert_to_markdown` 改 CLI 语法)
2. 运维:`mineru server start`(单条命令,本变更不写启动脚本)
3. 重启 FastAPI 服务
4. 验证:管理页文件管理 → 上传 PDF → 列表出现 + chunk 数 > 0 + `has_converted=true`;问答基于该 PDF 出真实答案
5. 回滚:`git revert` 即可,旧 loader.py 调旧版 CLI — 但旧 CLI 已经不存在,完全回滚需先降级 MinerU 二进制,通常没必要

## Open Questions

(无 — CLI 语法、tier 选择、产物路径都已确认)