# Design

## Context

参见 proposal.md - Why。当前状态:
- `~/mineru.json` 已配置 `models-dir.pipeline` + `models-dir.vlm` 指向 `~/.cache/modelscope/models/...`
- mineru-kit `models show` 报告期望路径 `~/.mineru/models/`,与实际下载位置不符;但 mineru 的旧版 `mineru.json` 配置可能仍被尊重
- 当前 `mineru server start` 跑的是 doclib server,parse-server 默认 disabled
- `app/rag/loader.py::convert_to_markdown` 用 `--tier flash`,产物无图片

## Goals / Non-Goals

**Goals:**
- 启用 local parse-server 模式,tier=basic
- loader.py 切到 `--tier basic`,产出含真实图片/版面/表格/公式的 markdown
- 复用已下载的 pipeline 模型集(2.4GB),不下载新模型
- 重新转换已有 flash 产物(覆写)

**Non-Goals:**
- 不引入 standard/advanced tier(VLM GGUF 缺)
- 不引入远程 `mineru.net` API
- 不改 `MINERU_ENABLED=false` 时的 UnstructuredReader 路径
- 不改 mineru server 启动脚本(运维文档后续跟进)

## Decisions

### D1. local mode=managed + managed_tier=basic
MinerU 本地 parse-server 默认 `mode=disabled`,要显式 enable。两个配置:
```
mineru config set parse_server.local.mode managed
mineru config set parse_server.local.managed_tier basic
```
然后 `mineru server start` 重启即可让 parse-server 跟随启动。`mode=managed` 由 MinerU 自己拉起 parse-server 子进程,无需手工 `pip install` + 配 systemd。
备选:`mode=server`(用外部 MinerU server URL)要额外部署;`mode=self_hosted` 要外部推理服务;`mode=embedded` 是内置,某些版本才有。

### D2. tier=basic(纯 pipeline backend)
basic tier = Layout + MFR + OCR + TabCls + TabRec,纯 pipeline,纯 CPU 可跑。
本机模型 2.4GB 已齐(`~/.cache/modelscope/models/OpenDataLab--PDF-Extract-Kit-1.0/`),无 VLM。精度 86.47 够 RAG + 人工核对用。
备选:`standard` 要 VLM GGUF,本机只有 safetensors 版,要下载或转格式,不采纳。

### D3. 重新转换时先删旧产物
`convert_to_markdown` 当前有 "产物已存在 → 复用" 优化,这次要让已 flash 转换过的 PDF 重新 basic 解析。
方案:开文档不删产物,而是给 `convert_to_markdown` 加个 `force` 参数,管理页上传路径传 `force=True`,产物存在也重新转换。
但更轻的方案:**直接删除 converted/ 里 PDF 已存在的旧 md**,再走默认路径(复用检查会落空,重新跑)。
本次决定:**改 loader.py 路径**(已上传 PDF 重新转换):直接在 convert_to_markdown 起首 `target.unlink(missing_ok=True)`,强制每次重转。理由是用户改 tier 的本意就是要刷新所有产物;后续若稳定下来再加 force 旋钮。

### D4. 不补 GGUF(避免下载)
VLM GGUF 模型大约 1-2GB,转换要 llama.cpp 量化的 GGUF 版。safetensors 模型不在 llama.cpp 默认路径上。
本次只跑 basic tier,pipeline 已够;不引入 GGUF。

### D5. 错误处理保留
basic tier 失败(超时 / non-zero / 空 stdout)继续抛 RuntimeError,与 flash 一致;不静默 fallback UnstructuredReader(用户希望看到 PDF 真的解析了)。

## Risks / Trade-offs

- [性能] basic tier pipeline 纯 CPU 解析 25 页 PDF 预计 30-90 秒,flash 0.3 秒;Mitigation:`MINERU_TIMEOUT_S` 默认 600 秒够用,前端可显示"转换中"toast(本次不变)
- [旧 flash 产物被覆写] converted/ 下所有 md 会被重新生成;Mitigation:本次明确 1 篇 PDF,影响小
- [parse-server 与 server 一起启动] 内存峰值:doclib server + parse-server + pipeline 模型 ~3-4GB,M4 16GB 够;Mitigation:监控内存,不够再降 tier
- [mineru.json vs mineru-kit 路径不一致] 旧版配置期望 modelscope,新版期望 ~.mineru;Mitigation:先试旧路径,不行再补符号链接
- [VLM 不可用] basic 不需要 VLM;Mitigation:无

## Migration Plan

1. 应用配置:`mineru config set parse_server.local.mode managed` + `managed_tier basic`
3. `mineru server restart`(让 parse-server 跟随)
4. 应用 code:loader.py `--tier flash` → `--tier basic`
5. 删除旧 flash 产物:`rm converted/*.md`
6. 重启 FastAPI
7. 验证:管理页上传 PDF → converted/ 新版 md 含真实图片引用;前端弹层显示图片
8. 回滚:配置 `mode=disabled` + loader.py 改回 `--tier flash`,5 秒内可逆

## Open Questions

(无 — 模型齐、tier 选 basic、错误处理保留)