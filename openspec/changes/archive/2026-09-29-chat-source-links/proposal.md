# Proposal

## Why

首页与管理页「参考来源」区块目前只显示来源名 + 置信度 + 200 字摘要,用户无法一键跳到原始出处核对 —— 知识库片段要手动去管理页翻转换 MD,Web / 小红书结果要点标题在浏览器里重新搜。来源本身已经带全部定位信息(web / xhs 的 `file_dir` 就是 URL,知识库 chunk 的 `doc_name` + `file_dir` 可拼出转换 MD 的代理 URL),只是管道没把跳转链接暴露给前端。

## What Changes

- **来源项新增 `url` 字段**:流水线来源构造(`app/rag/pipeline.py` `_build_sources` + 新增 `_source_url` 助手)按来源类型映射出可跳转链接:`web` / `xhs` 取召回文档的 `file_dir`(原 URL / 笔记链接);`vector`(知识库)按 `<stem>.md` 约定拼 `/converted/<stem>/<stem>.md`(经既有 `/converted` 代理路由,MinIO 回放);定位信息缺失(旧数据无 `doc_name` / `file_dir`)映射为 `None`,该条不渲染链接。
- **API 契约透出**:`app/api/chat.py` `SourceItem` 加 `url: str | None` 字段,非流式 `POST /chat` 与流式 `POST /chat/stream` 的 `meta` 事件来源列表同步携带(同一 `_build_sources` 构造,天然一致);落库 sources 带 url,历史回溯 / 管理页渲染的旧数据无 url 时前端照旧不渲染链接(向后兼容)。
- **前端来源行可点击跳转**:`static/app.js` `srcItemHtml`(首页流式 + 管理页历史共用)在来源名后渲染外链图标 + 链接文案,`url` 非空时整行来源名为可点击 `<a target="_blank" rel="noopener">`(新标签打开,不丢当前会话上下文);`url` 为 `null` 时保持现状纯文本渲染。新增外链 SVG 图标,样式随既有设计令牌(链接色 = 主色,hover 加深,无硬编码内联色)。
- **知识库链接 404 容错约定**:MinerU 未启用 / 未启用转换的文件没有 `converted/<stem>/<stem>.md` 对象,点击得到代理路由的 404 页 —— 属可接受的弱链接,不做服务端逐条存在性探测(避免每次问答多一轮 MinIO IO);管理页已有「查看转换MD」入口与 `has_converted` 标记可离线核对。

## Capabilities

### Modified Capabilities

- `chat-streaming`: 「答案来源携带 0-1 置信度」需求扩展为「来源项携带定位与跳转信息」—— 来源项 SHALL 额外携带 `url` 字段(0-1 置信度规则不变),并新增前端「来源行可点击跳转 / 缺 url 不渲染链接」的渲染要求(原「首页流式渲染」中来源块描述补充跳转语义)。
- `ui-style`: 新增「来源行跳转链接视觉」要求 —— 链接色随设计令牌、新标签行为、图标复用规则,两页一致。

## Impact

- **代码**:`app/rag/pipeline.py`(`_build_sources` + `_source_url`)、`app/api/chat.py`(`SourceItem.url`)、`static/app.js`(`srcItemHtml` + `SVG.link` + 历史回显同路)、`static/style.css`(`.src-link` 令牌化样式)。
- **兼容性**:纯增量字段 —— 非流式 / 流式 / 落库 JSON 多一个 `url` key,旧前端忽略、新前端读不到(旧数据)即降级纯文本;不影响置信度、低置信度提示、meta 统计任何既有行为。
- **不做的事**:不做逐来源详情补全(xhs `get_feed_detail`)、不做 kb 片段定位跳转(链接到整篇转换 MD,不做 chunk 锚点)、不在服务端探测 MinIO 对象存在性过滤死链。
