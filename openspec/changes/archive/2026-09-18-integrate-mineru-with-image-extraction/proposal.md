# Proposal

## Why

`upgrade-mineru-cli` 把 CLI 切到新版但用 `--tier flash`(纯文本占位符),`enable-mineru-basic-tier` 进一步切到 `--tier basic`(结构化文本但仍是占位符)—— 实测两种 tier 都出 `![Image block](doc:...)` 占位符,不写真实图片。RAG_agent 旧项目(`~/PycharmProjects/RAG_agent/pdf2md/`)基于 PyMuPDF 自带图片抽取,但当前 `Agentic-RAG-demo` 不该跨项目引入,我们要直接走新版 MinerU 的真出图入口:**`mineru-kit parse --tier basic -o <dir> -f markdown`**,它会把图片以 base64 内嵌进 md。需要后处理把 base64 抽到 `converted/<name>/images/`,md 改用相对路径引用 —— 这样图片真实落盘、RAG 检索不被 base64 噪声污染、前端"查看转换结果"弹层能渲染图片。

## What Changes

- `app/rag/loader.py::convert_to_markdown` 调用从 `mineru parse ...` 切到 `mineru-kit parse <path> --tier basic -o <tmpdir> -f markdown`,md 落 `<tmpdir>/<原文件名>.md`
- 同一函数新增后处理:解析 md 文本里的 `![](data:image/...;base64,...)` 内嵌 → 抽 bytes 写到 `MINERU_OUTDIR/<原文件名>/images/<sha前8>.<ext>`,md 文本里 base64 替换成相对路径 `images/<sha前8>.<ext>`,最终 md 写到 `MINERU_OUTDIR/<原文件名>.md`(保留原契约)
- `app/core/config.py` 暴露 `MINERU_OUTDIR_IMAGES_SUBDIR`(默认 `images`)常量,或直接 hardcode
- `main.py` 新增 `app.mount("/converted", StaticFiles(directory=str(Config.MINERU_OUTDIR)), name="converted")`,前端通过 `/converted/<name>/images/xxx.png` 直显(管理页"查看转换结果"弹层需要它)
- `app/api/upload.py::get_converted` 当前返回 md 文本不变,但前端弹层要支持 markdown 内 `![](images/xxx.png)` 自动转成 `/converted/...` 绝对 URL 才能渲染图片
- `static/app.js` `messageHtml` / `renderHistMessages` 中的 markdown 渲染路径不需改(它们是 chat 的来源/meta 渲染,不是 PDF 产物渲染) —— 仅 `manage.html` 的转换产物弹层要支持 markdown + 图片

## Capabilities

### Modified Capabilities
- `document-loading`:Scenario 增 "basic tier 启用后图片提取到 markdown(图片真实落盘,非占位符)"、`convert_to_markdown` 内置 base64 抽图与 md 重写、`/converted` 静态文件路由

## Impact

- `app/rag/loader.py`:重写 `convert_to_markdown`(从 ~30 行扩展到 ~80 行)
- `app/core/config.py`:加 `MINERU_OUTDIR_IMAGES_SUBDIR` 默认常量(或 inline)
- `main.py`:加 `app.mount("/converted", ...)`
- `static/manage.html`:转换产物弹层把 md 文本里的 `images/xxx.png` 链接自动 prefix 成 `/converted/<name>/images/xxx.png`
- 现有接口契约不变:`/upload/converted/{name}` 仍返回 `{name, content}`,`/upload/files` 仍含 `has_converted`
- 不影响 Milvus schema / 检索 / 重排

## 关系

- `enable-mineru-basic-tier`:已完成"MinerU 服务配置 + tier basic 模型齐"(`mode=managed`、`managed_tier=basic`、`mineru server start` + 模型 `MinerU-4_models_torch` 就绪),为本次变更提供前置依赖
- 本变更在 `enable-mineru-basic-tier` 之上做集成
- 与 `upgrade-mineru-cli`(CLI 语法层)无功能重叠,但配置变更后 `loader.py` 调用命令会替换