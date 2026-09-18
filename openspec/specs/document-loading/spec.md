# document-loading Specification

## Purpose
覆盖 PDF / DOCX / PPTX 经 MinerU 通道转 Markdown 入库的端到端契约:`mineru-kit parse`(tier=basic)调用语法、产物落盘与图片抽取(`converted/<stem>/` 每文档一文件夹)、入库文本图片引用规范化、错误语义、`MINERU_ENABLED` 开关行为。

## Requirements

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

### Requirement: parse-server 本地启用

系统 SHALL 在本地启动 MinerU parse-server(`mode=managed`,`managed_tier=basic`),由 `mineru server start` 拉起并常驻;调用方不感知具体 server 进程。

#### Scenario: parse-server 启动后可用
- **WHEN** `mineru server status` 报告 parse-server running 且 tier=basic
- **THEN** `mineru parse --tier basic` 调用成功,不被 "Local parse-server is disabled" 拒绝

#### Scenario: parse-server 失败
- **WHEN** parse-server 未起就调 `mineru parse --tier basic`
- **THEN** 报 "Local parse-server is disabled. Use --tier flash or --remote.",调用方应 fail-fast

### Requirement: MinerU 产物落盘与图片抽取

一份文档的 MinerU 产物 SHALL 集中在 `converted/<stem>/` 单一文件夹内(`stem` 为原文件名去掉后缀):md 产物为 `converted/<stem>/<stem>.md`,图片为 `converted/<stem>/images/<file>`,两者同级;`converted/` 顶层不再存放任何产物文件。`mineru-kit parse` 产物 md 里的 base64 内嵌图 SHALL 被抽取到该 `images/` 目录并在文本中替换为 `images/<hash>.<ext>` 相对引用;产物已存在时直接复用,不重复转换。

#### Scenario: 转换产物的落盘布局
- **WHEN** 一份名为 `报告.pdf` 的文档转换完成
- **THEN** md 落在 `converted/报告/报告.md`,图片落在 `converted/报告/images/` 下,`converted/` 顶层无散落的 md 文件

#### Scenario: 上传接口按新布局定位产物
- **WHEN** 管理页请求某 PDF 的转换产物(`has_converted` 判定与转换产物读取接口)
- **THEN** 系统按 `converted/<stem>/<stem>.md` 定位并返回内容,旧顶层路径不再被使用

#### Scenario: 图片落盘 + 路径替换
- **WHEN** 转换产物 md 含 `![](data:image/jpeg;base64,<base64string>)`
- **THEN** 后处理将 base64 解码为 jpeg 字节,写到 `converted/<stem>/images/<8字符hash>.jpeg`,md 文本该处被替换为 `images/<8字符hash>.jpeg`

#### Scenario: 多图按出现顺序落盘
- **WHEN** 一份 PDF 含 N 张图
- **THEN** `converted/<stem>/images/` 下生成 N 个文件,md 文本 N 处 base64 引用都被替换

#### Scenario: 落盘后 md 总大小明显小于 base64 内嵌
- **WHEN** 同一 PDF 转换产物对比
- **THEN** 经后处理的 md 文件大小应 < base64 内嵌版本的 30%(实测 7.9MB → 数十 KB)

#### Scenario: 产物已存在时跳过转换
- **WHEN** `converted/<stem>/<stem>.md` 已存在
- **THEN** 不调 mineru,直接返回该路径

### Requirement: 静态文件路由 `/converted`

系统 SHALL 在 FastAPI 挂载 `app.mount("/converted", StaticFiles(directory=str(Config.MINERU_OUTDIR)), name="converted")`,让前端通过 `/converted/<原文件名>/images/<hash>.<ext>` URL 直接访问图片二进制。

#### Scenario: 图片 URL 可 HTTP GET
- **WHEN** 浏览器请求 `/converted/<name>/images/<hash>.jpeg`
- **THEN** 返回 200 + image/jpeg 内容,不是 404

#### Scenario: 防路径穿越
- **WHEN** 浏览器请求 `/converted/../etc/passwd` 或 `/converted/<name>/../../../etc/passwd`
- **THEN** 返回 404,不返回任何文件

### Requirement: 入库文本图片引用规范化为绝对 URL

经 MinerU 通道转换入库的文档,进入切分与向量库的文本中,形如 `![alt](images/<file>)` 的相对图片引用 SHALL 被改写为 `![alt](/converted/<stem>/images/<file>)` 绝对 URL;落盘的 md 产物 SHALL 保持相对路径不变(人工核对与"查看转换结果"弹层行为不受影响)。

#### Scenario: 入库 chunk 含绝对 URL
- **WHEN** 一份含图 PDF 经上传入库完成
- **THEN** 向量库中该文档的 chunk 文本里图片引用形如 `![image](/converted/<stem>/images/<hash>.<ext>)`,不再是 `images/...` 相对路径

#### Scenario: 落盘产物保持相对路径
- **WHEN** 同一份 PDF 转换完成
- **THEN** `converted/<stem>/<stem>.md` 中的图片引用仍为 `images/<hash>.<ext>` 相对路径,文件内容不因本变更改变

#### Scenario: 已有产物复用时同样改写
- **WHEN** `converted/<stem>/` 下已存在该文件的转换产物,重新上传入库(产物直接复用)
- **THEN** 入库 chunk 文本中的图片引用仍被规范化为绝对 URL

### Requirement: 原生 Markdown 直传不做路径改写

`.md` / `.markdown` 文件直传入库时,其文本中的图片引用 SHALL 保持原样,不做任何路径改写或搬运(此类文件的图片语义由作者自行负责,系统不猜测其存放位置)。

#### Scenario: 直传 md 引用不被改写
- **WHEN** 用户直传一份图片引用为 `./assets/a.png` 的 `.md` 文件并入库
- **THEN** 向量库中该文档 chunk 的文本保留 `./assets/a.png` 原文
