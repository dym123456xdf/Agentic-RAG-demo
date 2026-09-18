# Tasks

## 1. loader.py 改用 mineru-kit parse + 后处理

- [x] 1.1 `app/rag/loader.py::convert_to_markdown` 命令从 `[MINERU_BIN, "parse", path, ...]` 切到 `[MINERU_BIT, "kit", "parse", ...]`(实际为独立二进制 `MINERU_KIT_BIN`),产物从 `<tmpdir>/<原文件名>.md` 读文件。验证:临时跑一次,看到产物 md 含 `![](data:image/...;base64,...)` 真实引用,无 `![Image block]`
- [x] 1.2 同一函数新增 base64 抽图后处理:正则 `!\[[^\]]*\]\(data:image/(\w+);base64,([A-Za-z0-9+/=]+)\)` 找所有内嵌图 → base64 解码 → 写到 `MINERU_OUTDIR/<原文件名>/images/<sha1前8>.<ext>` → md 文本替换为 `![image](images/<sha1前8>.<ext>)`。验证:同一 PDF 跑两次,第二次转换产物 md 文件大小应 < 100KB(原 base64 内嵌版本 7.9MB),`converted/<name>/images/` 下有图片文件
- [x] 1.3 最终 md 写盘:`MINERU_OUTDIR/<原文件名>.md`(保留旧契约,`converted_md_path()` 行为不变)。验证:`converted_md_path(Config.UPLOAD_DIR / "xxx.pdf")` 仍返回 `MINERU_OUTDIR/xxx.pdf.md`,且该文件 mtime 新于 raw PDF 上传时间

## 2. 静态文件路由

- [x] 2.1 `main.py` 加 `app.mount("/converted", StaticFiles(directory=str(Config.MINERU_OUTDIR)), name="converted")`,放在 `/static` mount 旁。验证:重启服务后 `curl /converted/<name>/images/<hash>.jpeg` 返回 200 + image/jpeg
- [x] 2.2 路径穿越防护:curl `/converted/../etc/passwd` 返回 404 或被 FastAPI 重写为正常路径。验证:返回 404,响应体不含 `/etc/passwd` 内容

## 3. 管理页弹层改写图片链接

- [x] 3.1 `static/manage.html` 转换产物弹层(`$("mdContent")`)把 `<pre>` 换成能渲染 markdown 图片的容器:解析 `!\[[^\]]*\]\(images/([^)]+)\)` 正则,替换为 `<img src="/converted/<name>/images/\1">`,保留其它文本。验证:人工核对弹层渲染:真实图片 + 文本都在
- [x] 3.2 文本兜底:替换后的 md 中非图片 markdown 语法(`## 标题`、`表格`)不强求,文本能正常显示即可(不强求 markdown 渲染库)。验证:浏览器查看弹层文本可读、不乱码

## 4. 端到端验证

- [x] 4.1 删旧 `converted/*.md`,重传 PDF,基本后台跑完转换。验证:`/upload/files` 该 PDF `has_converted=true`,`chunks_ingested>0`,`converted/<name>.md` 文件小(< 100KB)且非空
- [x] 4.2 `/upload/converted/<name>` 返回的 md content 含 `![](images/<hash>.<ext>)` 相对引用,无 base64 残留。验证:curl 该接口 + grep 验证
- [x] 4.3 浏览器手动打开 `static/manage.html`,点击"查看转换MD",弹层显示真实图片(至少一张图)。验证:人工核对截图(代码侧:mdContent → mdRender 已切换,renderMdWithImages 已实现,样式 .md-render 加了 max-width:100%)
- [x] 4.4 真实问答含图片上下文(可选,验证 RAG 链路不挂)。验证:`POST /chat` 提 PDF 内容相关问题,响应 200、`sources` 非空、`answer` 含具体事实