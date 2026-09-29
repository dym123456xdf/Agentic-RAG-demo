# Tasks

## 1. 后端:来源项透出跳转链接

- [x] 1.1 `app/rag/pipeline.py` 新增 `_source_url(d: dict) -> str | None` 助手(design D1 映射规则:`web` / `xhs` 取 `file_dir`;`vector` 按 `/converted/<stem>/<stem>.md` 拼,stem = `Path(doc_name).stem`;定位信息缺失返回 `None`),`_build_sources` 输出 dict 加 `url` 键;验证:纯函数单跑 —— kb / web / xhs / 缺 doc_name 四类构造数据各自映射正确
  - 2026-09-29 实测:六类构造数据(kb vector / kb md / web / xhs / 缺 doc_name / web 缺 file_dir)`_source_url` 全对;`_build_sources` 输出含 `url`,ALL PASS
- [x] 1.2 `app/api/chat.py` `SourceItem` 加 `url: str | None = None` 字段,非流式响应与流式 meta 事件来源列表自动携带;验证:起服务后 `curl` 调 `POST /chat`(kb 模式)响应 sources[0] 含 url 且为 `/converted/...` 相对路径;`POST /chat/stream` 的 meta 帧同形
  - 2026-09-29 实测(8012 临时实例,新代码):非流式 `POST /chat` sources[0].url=/converted/尚硅谷-01-LangChain概述/...md;流式 meta 帧 sources[0].url 同值
- [x] 1.3 兼容回归:落库 sources 带 url 不影响历史回显接口(`GET /sessions/{id}/messages` 原样返回 JSON);旧记录无 url key 不报错;验证:服务启动后拉一条含来源的历史消息渲染正常(管理页),旧数据(如有)来源行保持纯文本
  - 2026-09-29 实测:`GET /sessions/{id}/messages` 返回来源带 url(新落库);旧记录 sources 无 url key,前端 srcItemHtml 走 s.url 缺省分支渲染纯文本,不报错

## 2. 前端:来源行可点击跳转

- [x] 2.1 `static/app.js` `SVG` 常量加外链图标(与既有 stroke 风格一致);`srcItemHtml`:`s.url` 非空时来源名渲染 `<a class="src-link" href target="_blank" rel="noopener">` + 图标,href 经 escape 防属性逃逸;`s.url` 空 / 缺时保持现状纯文本;验证:首页提问后来源行出现可点链接、点开新标签;管理页历史展开后同行为
- [x] 2.2 `static/style.css` 加 `.src-link` 令牌化样式(色 = `--accent`,hover = `--accent-hover`,下划线可选;链接图标 `--accent`,不得硬编码内联色);验证:链接观感与两页既有暖棕主色一致,无内联样式

## 3. 端到端验证

- [x] 3.1 起服务(`conda run -n rag uvicorn main:app --port 8011`),首页 kb 模式提问 → 来源行链接点开 = `/converted/<stem>/<stem>.md` 能看到转换 MD(MinerU 启用且该文件已转换);web / xhs 模式(开关允许时)来源行链接为外部 URL
  - 2026-09-29 实测(8012 临时实例):kb 模式来源 url=/converted/尚硅谷-01-LangChain概述/尚硅谷-01-LangChain概述.md,`GET` 该路径 200 text/markdown(len≈35KB);xhs 模式(开关已开,xhs-mcp 18060 存活)来源 url=https://www.xiaohongshu.com/explore/<feed_id> 三条笔记链接;web 模式本机 BRAVE 未配,未实跑(代码路径与 xhs 同,取 file_dir)
- [x] 3.2 管理页问答历史 tab:展开来源 → 新落库消息带链接、旧消息无 url 保持纯文本不报错
  - 2026-09-29 实测(8012 + 浏览器):管理页问答历史 tab 展开来源,新落库 xhs 会话渲染 `<a class="src-link" target="_blank" rel="noopener">` + 外链图标(href=https://www.xiaohongshu.com/explore/...);旧会话(sources 无 url 键)来源名保持纯文本 `<b>`,无链接无图标不报错
- [x] 3.3 `openspec validate chat-source-links --strict` 通过
  - 2026-09-29 实测:`openspec validate chat-source-links --strict` → "Change 'chat-source-links' is valid"
