# Design

## Context

参见 proposal.md - Why。现状:
- `enable-mineru-basic-tier` 已完成配置(parse-server 起、managed_tier=basic、MinerU-4_models_torch 模型齐)
- `app/rag/loader.py::convert_to_markdown` 仍用 `mineru parse --tier basic --wait N --pages 1-1000 --limit N`(stdout-only 路径,产物是 markdown 文本流 + 占位符)
- 实测 `mineru-kit parse --tier basic -o <tmpdir> -f markdown` 能产出含真实 base64 图片的 md,7.9MB 单文件(全是 base64)
- 当前 `/upload/converted/{name}` 接口返回 md content,管理页弹层用 `<pre>` 渲染纯文本,图片无法显示

## Goals / Non-Goals

**Goals:**
- `convert_to_markdown` 走 `mineru-kit parse -o <tmpdir> -f markdown`
- 后处理:base64 内嵌图抽到 `MINERU_OUTDIR/<name>/images/`,md 文本 base64 替换成相对路径
- 顶层 md 写到 `MINERU_OUTDIR/<name>.md`(保留既有契约:`converted_md_path()` 行为不变)
- FastAPI `/converted` 静态路由,前端能 HTTP GET 图片
- 管理页弹层改写 `images/` → `/converted/<name>/images/` 让图片可渲染

**Non-Goals:**
- 不改 MinerU tier 或下新模型(沿用 basic + 已下模型)
- 不引入 markdown HTML 渲染库(如 markdown-py);前端用最简的 src 替换即可
- 不改 Milvus schema 或 chunking
- 不支持 DOCX/PPTX 的图片抽(本变更聚焦 PDF;DOCX/PPTX 通过同样的 base64 路径应可用,但暂不在 spec 范围)

## Decisions

### D1. 用 `mineru-kit parse` 而非 `mineru parse`
两个 CLI 名字相近但行为迥异:
- `mineru parse`:doclib client,stdout markdown 文本流,无图片落盘
- `mineru-kit parse`:独立 CLI,`-o <dir> -f markdown` 输出到目录,产物含 base64 内嵌图片
两者底层都调 `mineru.backend.analyze.doc_analyze`,但 CLI 包装层行为不同。
本变更固定用 `mineru-kit parse`(`/opt/anaconda3/envs/rag/bin/mineru-kit`)。

### D2. base64 抽图用正则 `data:image/(\w+);base64,([A-Za-z0-9+/=]+)`
`![](data:image/jpeg;base64,<...>)` 形态,MinerU 输出统一。base64 解码后写到 `<hash>.<ext>`,hash 用前 8 字符 SHA1(短到不爆栈,长到去重)。

### D3. 图片目录:MINERU_OUTDIR/<原文件名>/images/
顶层 md 仍在 `MINERU_OUTDIR/<原文件名>.md`(保留旧契约,`converted_md_path()` 不变),图片下移一层 `images/` 子目录(避免和 md 同级混乱,前端引用 `images/xxx` 即可)。

### D4. FastAPI mount /converted 静态文件
```python
app.mount("/converted", StaticFiles(directory=str(Config.MINERU_OUTDIR)), name="converted")
```
在 `main.py` 已有的 `/static` mount 旁加这一条。FastAPI StaticFiles 自带路径穿越防护(`..` 会被规范化为 `converted/images/..`,目录不存在 → 404)。
注意:`MINERU_OUTDIR` 必须已存在(`Config.ensure_dirs()` 已经创建)。

### D5. 前端改写:`images/xxx` → `/converted/<name>/images/xxx`
管理页弹层拿到 md content 后,**客户端**做简单字符串替换(仅 `src=` 替换,不解析 markdown):
```js
mdContent.replace(/\]\(images\//g, `](/converted/${encodeURIComponent(name)}/images/`);
```
弹层用 `<pre>` 渲染 vs markdown 渲染?现状用 `<pre>`(管理页 code 177 行 `mdContent.textContent = d.content`),需要换 `<pre>` 为 markdown-friendly 容器 + 简单图片渲染。
最简方案:正则找 `!\[[^\]]*\]\(images/[^)]+\)` 替换为 `<img>` 标签,其余 text 走 `<pre>` 兜底。或者更简单 — 用 marked.js 等。
本变更用最简方案:**仅替换 `![](images/X)` 为 `<img src="/converted/.../X">`**,其它 markdown 语法不强求渲染(对 PDF 文本内容来说够用)。

### D6. 不下新模型
`enable-mineru-basic-tier` 已下完 `MinerU-4_models_torch`(2.4GB),本变更复用。`mineru-kit parse` 启动时会自动调起 doclib + parse-server(因为 mode=managed),无需手工 server start。

### D7. 错误语义保留
`mineru-kit parse` 失败(非零退出 / 超时 / 无 md):抛 RuntimeError,带 returncode 与文件名,不静默 fallback UnstructuredReader。
新增场景:产物 md 含 base64 但解码失败 → 跳过该图片,日志告警,其它图片继续处理(尽力而为)。

## Risks / Trade-offs

- [大 PDF base64 解码慢] → 47 张图 7.9MB 解码 < 5 秒;Mitigation:同步处理,接受
- [md 文本里的 base64 字符串里包含 `)` 会让正则断尾] → base64 字符集 `[A-Za-z0-9+/=]`,不含 `)`;Mitigation:正则用 `\([^)]+\)`
- [前端弹层改写后 `<pre>` 仍显示 `<img>` 标签原文] → 改用 `<div class="md-render">` 容器,把 `<img>` 标签作为 HTML 插入;Mitigation:简单插入风险(XSS),但内容来自服务端 md,MinerU 不会在 md 里塞 `<script>`
- [FastAPI StaticFiles 把整个 MINERU_OUTDIR 暴露] → 用户能列 `converted/` 目录或拿到别人 PDF 的 md;Mitigation:目录已经放了 md,本来就是产物查看接口的 backend 源;前端只对已上传文件路径生成 URL,无信息泄露加剧
- [OCR 性能] 25 页 PDF basic tier 实测 1.x 秒;Mitigation:`MINERU_TIMEOUT_S=600` 够用

## Migration Plan

1. 应用本次代码变更(`convert_to_markdown` 重写 + main.py 加 mount)
2. 删除旧 flash 产物:`rm -f converted/*.md`(避免旧产物干扰)
3. 重启 FastAPI
4. 重传 PDF,验证:
   - converted/<name>.md 文件小(非 7.9MB)
   - converted/<name>/images/*.png 多个真实图片
   - md 文本里 `![](images/...)` 引用,无 base64
5. 浏览器打开管理页 → 弹层显示真实图片
6. 回滚:`loader.py` 旧版本 + 移除 mount,5 秒内可逆

## Open Questions

(无 — CLI 路径已确认出图、抽图正则明确、静态路由方案清晰)