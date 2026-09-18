# Spec Delta

## Purpose

将 `document-loading` 能力的 PDF→MD 通道切到新版 MinerU 的真出图入口 `mineru-kit parse`,并在 loader.py 里内置 base64 图片抽取 + md 相对路径改写,让图片真实落盘到 `converted/<name>/images/`,前端"查看转换结果"弹层能渲染真实图片(不再有 `![Image block]` 占位符)。

## MODIFIED Requirements

### Requirement: 新版 MinerU CLI 调用契约

系统 SHALL 通过 `mineru-kit parse <path> --tier basic -o <tmpdir> -f markdown` 调用 MinerU,使产物 md 含真实图片(以 base64 内嵌形式),不被 `mineru parse` 那套 stdout-only 的 `![Image block](doc:...)` 占位符污染。

#### Scenario: 产物 md 含真实图片
- **WHEN** 上传一份含图的 PDF 并转换
- **THEN** `<tmpdir>/<原文件名>.md` 含 `![](data:image/jpeg;base64,...)` 或 `![](data:image/png;base64,...)` 真实图片引用,而非 `![Image block](doc:...)` 占位符

#### Scenario: 不再用 stdout-only 的 mineru parse
- **WHEN** `convert_to_markdown` 被调用
- **THEN** 子进程命令以 `mineru-kit parse` 开头(不是 `mineru parse`),并包含 `-f markdown` 与 `-o <dir>`

#### Scenario: 旧版调用已下线
- **WHEN** 任何代码路径触发 MinerU 转换
- **THEN** 子进程命令行包含 `parse` 子命令,不含旧版 `-p path -o dir` 形态

#### Scenario: 显式 tier
- **WHEN** 调用 MinerU 转换 PDF/DOCX/PPTX
- **THEN** 命令行必须包含 `--tier basic`,产物含图片/版面/表格/公式的完整解析;`flash` 为纯文本提取(图片只出 `![Image block](doc:...)` 占位符),不再采用

#### Scenario: 表格与公式保留
- **WHEN** 上传一份含表格或 LaTeX 公式的 PDF
- **THEN** 转换产物保留表格 markdown 结构或 `$...$` / `$$...$$` 公式,非空文本

## REMOVED Requirements

### Requirement: 一次拉全部页

`--pages/--limit/--wait` 是 stdout-only 的 `mineru parse` 分页参数;`mineru-kit parse -o <dir>` 一次调用直接产出整个文档的全部产物,无分页语义,该约束随 CLI 切换消失。

### Requirement: 产物落盘到 `converted/<原文件名>.md`

落盘契约由「MinerU 产物落盘与图片抽取」整体取代:md 落盘之外新增 base64 图片抽取与相对路径化语义,原顶层单文件契约不再单独成立。

## ADDED Requirements

### Requirement: MinerU 产物落盘与图片抽取

系统 SHALL 解析 `mineru-kit parse` 产物 md 文本里的 base64 内嵌图片,提取二进制写到 `MINERU_OUTDIR/<原文件名>/images/<hash>.<ext>`,并把 md 文本里的 base64 引用替换成 `images/<hash>.<ext>` 相对路径。最终 md 写到 `MINERU_OUTDIR/<原文件名>.md`;产物已存在直接复用,不重复转换。

#### Scenario: 图片落盘 + 路径替换
- **WHEN** 转换产物 md 含 `![](data:image/jpeg;base64,<base64string>)`
- **THEN** 后处理将 base64 解码为 jpeg 字节,写到 `MINERU_OUTDIR/<原文件名>/images/<8字符hash>.jpeg`,md 文本该处被替换为 `images/<8字符hash>.jpeg`

#### Scenario: 多图按出现顺序落盘
- **WHEN** 一份 PDF 含 N 张图
- **THEN** `MINERU_OUTDIR/<原文件名>/images/` 下生成 N 个文件,md 文本 N 处 base64 引用都被替换

#### Scenario: 落盘后 md 总大小明显小于 base64 内嵌
- **WHEN** 同一 PDF 转换产物对比
- **THEN** 经后处理的 md 文件大小应 < base64 内嵌版本的 30%(实测 7.9MB → 数十 KB)

#### Scenario: 产物已存在时跳过转换
- **WHEN** `converted/<原文件名>.md` 已存在
- **THEN** 不调 mineru,直接返回该路径

### Requirement: 静态文件路由 `/converted`

系统 SHALL 在 FastAPI 挂载 `app.mount("/converted", StaticFiles(directory=str(Config.MINERU_OUTDIR)), name="converted")`,让前端通过 `/converted/<原文件名>/images/<hash>.<ext>` URL 直接访问图片二进制。

#### Scenario: 图片 URL 可 HTTP GET
- **WHEN** 浏览器请求 `/converted/<name>/images/<hash>.jpeg`
- **THEN** 返回 200 + image/jpeg 内容,不是 404

#### Scenario: 防路径穿越
- **WHEN** 浏览器请求 `/converted/../etc/passwd` 或 `/converted/<name>/../../../etc/passwd`
- **THEN** 返回 404,不返回任何文件
