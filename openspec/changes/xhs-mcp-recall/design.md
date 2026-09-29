# Design

## Context

现状(见 proposal.md - Why):`mcp_client.call_tool()` 只走 stdio(进程内拉起自建 `python -m mcp_server`,Brave Web 搜索用);查询图三路召回并行扇出,`route_after_preprocess` 按意图 + 开关决定挂载哪些路(Web 路 = factual 意图 × `WEB_SEARCH_ENABLED`);`web_search` 节点自捕异常降级空路,不阻断图。本次接入的 xiaohongshu-mcp 是**外部独立部署**的 Go 服务(Streamable HTTP,`http://127.0.0.1:18060/mcp`,真实账号 cookie 鉴权,搜索走无头浏览器),生命周期与本服务完全解耦 —— 传输层必须新增 HTTP 通道,可用性必须按「可降级」对待。产品要求(已与用户确认):**搜索模式互斥** —— 下拉三选一(kb / web / xhs),选外部不查库、选库不外调,不做并行叠加。

## Goals / Non-Goals

**Goals:**

- `mcp_client` 双 transport 并存:stdio(Brave,不动)+ Streamable HTTP(外部服务,带可选 Bearer 鉴权)。
- `xhs_search` 作为小红书模式的唯一召回路:挂载、融合、meta 统计、前端阶段文案全部打通。
- 搜索模式用户可选且互斥:前端下拉 → 请求参数 → 查询图互斥路由,选项按部署可用性过滤、记住上次选择。
- 任何小红书侧重故障(服务未启动 / 登录态失效 / 超时 / 响应异常)都不影响问答主链路。

**Non-Goals:**

- 不做 `get_feed_detail` 详情补全(每条笔记一次无头浏览器导航,N+1 太慢;标题+摘要的文本厚度与 Brave snippet 同级,交给重排过滤)。
- 不做外部 + 本地并行融合(用户已确认互斥;将来要加再走新变更)。
- 不把小红书笔记入库(与 Web 召回同语义:仅本轮可见)。
- 不部署、不管理 xiaohongshu-mcp 服务本身(用户自行下载二进制 / Docker + 扫码登录)。
- 不做逐来源的开关记忆持久化到服务端(选择只存前端 localStorage,不进 MySQL)。

## Decisions

### D1:mcp_client 按「每次调用独立建连」加 HTTP 通道,不做持久会话

`call_tool_http(url, tool_name, arguments, headers=None)`:用 `mcp.client.streamable_http.streamablehttp_client(url, headers=...)` + `ClientSession` 上下文管理器,一次调用 = 建连 + initialize 握手 + call_tool + 关闭。理由:
- 与现有 stdio 的每调用生命周期完全同构,代码心智一致;
- `xhs_search` 每次查询最多触发一次,localhost 建连开销毫秒级,持久会话收益为零;
- 持久会话要处理断线重连、FastAPI 多 worker 共享等生命周期问题,复杂度不划算。

现有 `call_tool()`(stdio)签名与行为保持不变,Brave 路径零改动。头部 docstring 从「为什么 stdio」改写为「双 transport:stdio 自建服务 / HTTP 外部服务」。

### D2:超时上限 60s,由节点层 asyncio.wait_for 兜底

`rrf_fuse` 汇合语义 = 等全部挂载路完成,小红书无头浏览器搜索可能耗时数秒到数十秒;不设上限会拖死整条回答。在 `xhs_search` 节点用 `asyncio.wait_for(…, 60)` 包住整次 HTTP 调用,超时与其它异常同路降级(空列表 + warning 日志)。选 60s:低于前端 SSE 常见代理空闲超时,高于无头浏览器冷启动(首次 ~150MB 下载不算在内 —— 那是服务侧进程自己的事)。

### D3:节点自己捕异常降级,不依赖 BaseNode 包装

`BaseNode.__call__` 会把 `process()` 异常包成 `QueryProcessError` 重抛、终止整图 —— 对外部依赖路这是错误语义。`NodeXhsSearch.process` 与 `NodeWebSearch` 同款:`try/except Exception` 全捕 → 空 `xhs_search_docs` + `self.logger.warning`,图继续(xhs 模式下降级后按空召回走重排与生成,答案如实说不知道,不编造)。

### D4:结果规范化 + 防御性字段提取

`search_feeds(keyword)` 返回 TextContent 里的 JSON(笔记列表,含 `note_id` / `xsec_token` / 标题 / 作者等)。字段名以实测为准,提取时逐字段 fallback(如 `title` → `display_title` → `desc`),取前 `XHS_SEARCH_LIMIT` 条(默认 5)规范化:

```
text = 标题 + 摘要(若有)     # 重排与生成的文本主体
doc_name = 标题               # 前端来源名
file_dir = 笔记链接           # https://www.xiaohongshu.com/explore/<note_id>
metadata = {source_type: "xhs", feed_id, xsec_token}  # token 留给未来的详情补全
score = 1.0, chunk_idx = 0
```

`_doc_id_of` 加 `xhs::` 前缀分支(与 `web::` 对称),保证融合去重标识稳定。

### D5:模式互斥路由 —— 选择即全量,不做叠加(用户已确认)

`route_after_preprocess` 改为按模式决策:

```
chitchat            → 直达 cliff_rerank(不变)
search_mode == "kb" → embedding_search +(HYDE_ENABLED 且 intent ∈ {factual, explanatory} 时)hyde_search
search_mode == "web"→ web_search(仅此一路)
search_mode == "xhs"→ xhs_search(仅此一路)
```

理由:用户下拉选择表达的是「这轮就用这个查」,显式意图优先于意图分类的隐式猜测;互斥执行避免无用的向量检索 / HyDE LLM 调用 / 外部调用 —— 每次提问只花该花的钱。HyDE 的意图规则保留在 kb 模式内不动(它是向量检索的质量增强,与外部检索无关)。RRF 与断崖重排节点保持串在图里:单路模式下 RRF 退化为单路重排(等价透传),断崖重排继续对 Web / 小红书 snippet 做质量截断 —— 图结构不用拆,只是挂载的路变少。

### D6:选择链路 = 请求参数 search_mode,三值枚举,不可用模式显式拒收

- `ChatRequest` 加 `search_mode: Literal["kb", "web", "xhs"] = "kb"`;非法值由 Pydantic 自动 422;**取值合法但对应主开关未启用**(如 `web` 但 `WEB_SEARCH_ENABLED=false`)在 `_resolve` 校验层返回 4xx —— 互斥模式下选了不可用的路等于什么都不查,静默吞掉会答非所问,显式拒收最诚实。前端已按可用性过滤,正常用户不会触达。
- `pipeline.query / query_stream` 加同名参数,注入 `create_default_query_state(search_mode=...)` → 状态字段 → `route_after_preprocess` 读状态。API 层只做参数组装,符合「业务逻辑进图」规范。
- 新增 `GET /api/config` 返回 `{web_search_enabled, xhs_enabled}`(只读布尔,不含任何密钥);前端加载时拉取,决定下拉选项。为什么不做成「下拉恒显 3 项、选了不可用的静默跳过」:互斥模式下静默跳过 = 空检索 +「我不知道」,用户会当成功能坏了;按可用性过滤 + 不可用不出现,语义诚实。端点放独立小路由(如 `app/api/config.py`),挂到 main.py。
- 状态契约加 `search_mode: str = "kb"` 默认值,旧调用不传时行为不变。

### D7:前端下拉 —— 输入区旁原生 select 三选项,localStorage 记忆

`static/index.html` 输入区(发送按钮旁)加 `<select id="search-mode">`:选项「仅知识库 / 联网搜索 / 小红书」;页面加载时按 `GET /api/config` 结果增删(仅知识库恒在;两个外部源都不可用时整个下拉隐藏,页面回到现状);`static/app.js` 提交提问时把选中值放进请求体 `search_mode`,并用 `localStorage["search_mode"]` 恢复 / 记忆(恢复值不可用则回落仅知识库)。用原生 select 而非自定义组件:单选、三项、无图标需求,样式跟随现有输入区(ui-style 的既有视觉语言)。不提供「联网 + 小红书」组合项(用户已确认:三选一,要查两路就问两次)。

### D8:阶段文案与 meta 按模式如实呈现

`_STAGE_MSGS` 注册 `xhs_search: "小红书检索完成…"`;`preprocess` 之后的召回阶段文案按模式区分(kb:「多路召回中(向量 + HyDE)…」;web:「联网检索中…」;xhs:「小红书检索中…」),避免外部模式下仍显示"向量召回"误导用户。`meta.recall_paths` 按实际挂载路输出(kb → dense/hyde,web → web,xhs → xhs),`raw_count` 同步按模式统计。

## Risks / Trade-offs

- [纯外部模式答案质量完全依赖外部 snippet(标题 + 摘要,无 KB 兜底)] → 断崖重排 + 低置信度提示仍生效;snippet 太薄时宁可「不知道」也不编造,符合产品定位。
- [外部路降级(xhs 服务挂)后该模式无任何结果] → 答案如实说不知道;前端下拉仍可选(服务启动期不探测),属已知权衡。
- [登录态失效(cookie 过期)] → 降级空路 + warning 日志;用户侧重跑 xiaohongshu-login 扫码即可,本服务无需改动。
- [search_feeds 响应结构与假设不符] → 防御性提取 + 解析失败降级空路;apply 阶段实测一次并校正字段映射,不改架构。
- [同账号多处网页端登录会互踢] → 属服务侧使用约束,写进 `.env` 注释与 CLAUDE.md 提示。
- [mcp SDK 版本过旧没有 `streamablehttp_client`] → apply 第一步先验证 import;缺则在 rag 环境内升级 `mcp` 包(2.x 内升级,stdio API 兼容)。
- [默认不再自动联网,老用户感知变化] → 属有意的产品决策(proposal 已标注 BREAKING 语义);前端下拉常驻可见,入口损失小。
- [localStorage 记住的选择在主开关关闭后失效] → 恢复时校验可用性,不可用回落「仅知识库」。

## Migration Plan

纯增量、默认行为等同现状(`search_mode` 缺省 kb = 向量 + HyDE)。启用顺序:① 用户部署 xiaohongshu-mcp 并扫码登录;② `.env` 配 `XHS_MCP_ENABLED=true`(+ 可选 URL / TOKEN)、确认 `WEB_SEARCH_ENABLED` 与 Brave key 状态;③ 重启 rag 服务;④ 前端刷新,下拉出现可用选项。回滚 = 关主开关重启,下拉自动收敛(两源均不可用时整体隐藏)。无数据迁移,历史问答不受影响。
