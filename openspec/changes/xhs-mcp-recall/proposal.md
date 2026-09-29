# Proposal

## Why

知识库现有三路召回(向量 / HyDE / Brave Web)由后端配置 + 意图「暗控」,用户不可见、不可选,且不论用户想要什么都会并行跑多路 —— 费资源、做无用功。本次引入**搜索模式互斥路由**:首页下拉三选一(仅知识库 / 联网搜索 / 小红书),选哪路只跑哪路;同时接入 [xpzouying/xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp)(Streamable HTTP,本地独立部署)作为小红书模式的召回源。

## What Changes

- **搜索模式互斥路由(核心行为变化)**:`search_mode ∈ {kb, web, xhs}` —— `kb` 走向量 + HyDE(按现行意图规则);`web` 仅走 Web 搜索;`xhs` 仅走小红书搜索。任一时刻只执行用户选中的一类检索,外部模式不查本地库,`kb` 模式不发起外部调用;`chitchat` 意图任何模式都跳过全部召回。
- 首页输入区新增下拉列表(仅知识库 / 联网搜索 / 小红书),选项按 `GET /api/config` 返回的主开关可用性过滤,两外部源均不可用时下拉整体隐藏;选择随每次提问发送(`search_mode` 请求参数),localStorage 记住上次选择。
- `app/core/mcp_client.py` 新增 HTTP(Streamable HTTP)transport 的通用 `call_tool_http()`:现有 stdio 路径(Brave 自建 server)不动。
- 新增 `xhs_search` 查询节点(async):调 `search_feeds` 搜索小红书笔记,规范化为与 Web 召回同形的文档(`source_type="xhs"`),失败 / 超时(60s)降级为空路,不阻断查询。
- `rrf_fuse` 融合范围收窄为「当前模式挂载的路」:`kb` 至多两路,`web` / `xhs` 单路(退化为单路重排);等权与 k=60 不变。
- `route_after_preprocess` / 查询图装配 / 状态契约 / `pipeline.py`(参数透传 + meta 统计 + 阶段文案)同步改造。
- `config.py` 新增 `XHS_MCP_ENABLED` / `XHS_MCP_URL` / `XHS_MCP_TOKEN` / `XHS_SEARCH_LIMIT`;启用时只校验 URL 非空 —— 服务本体由用户独立部署(需扫码登录),启动期不做网络探测,运行期失败降级。

## Capabilities

### New Capabilities

- `search-mode-selection`: 搜索模式的用户选择链路 —— 首页下拉选择器、`GET /api/config` 可用性端点、chat 请求的 `search_mode` 参数(kb / web / xhs 三值互斥)、模式到查询图挂载的互斥路由语义。

### Modified Capabilities

- `multi-path-recall`: 新增「MCP HTTP transport 客户端」「小红书 MCP 召回节点」「RRF 模式内融合」「小红书结果仅本轮可见」要求;「HyDE 假设文档生成」「Web 搜索节点」挂载条件加模式约束(HyDE 仅 kb;Web 仅 web 模式);原「RRF 倒数排名融合」(三路同框)移除,由模式内融合取代。
- `langgraph-orchestration`: 「查询图装配」(多路并行扇出)移除,由「查询图模式路由装配」取代 —— 图结构与两个编译产物不变,条件路由依据变为搜索模式 + 意图 + 开关。
- `chat-streaming`: 流式问答接口请求体由 `{question, session_id}` 扩为 `{question, session_id, search_mode}`,两出口(流式 / 非流式)一致。

## Impact

- **代码**:`app/core/mcp_client.py`(HTTP 客户端 + docstring 双 transport 说明)、`app/core/config.py`(4 个新配置项 + validate)、`app/rag/nodes/query_nodes.py`(新节点 + 路由函数改模式互斥 + RRF 模式内融合 + `_doc_id_of` xhs 分支)、`app/rag/query_graph.py`(节点注册 + 条件边)、`app/rag/state.py`(`xhs_search_docs` / `search_mode` 字段)、`app/rag/pipeline.py`(参数透传 + meta 统计 + 按模式阶段文案)、`app/api/chat.py`(`search_mode` 参数 + 不可用模式拒收)、`app/api/`(新增 config 端点路由)、`static/index.html` + `static/app.js`(下拉选择器 + localStorage 记忆)。
- **外部依赖**:用户需自行部署 xiaohongshu-mcp 服务(二进制 / Docker,默认 `http://127.0.0.1:18060/mcp`)并扫码登录;该服务是外部进程,不进本仓库、不进 requirements。MCP Python SDK 已有的 `streamablehttp_client` 即可支撑,无需新增 Python 依赖。
- **兼容性**:`search_mode` 缺省 `kb` —— 不传该参数行为与现状一致(向量 + HyDE);**BREAKING 语义**:`WEB_SEARCH_ENABLED=true` 不再让 factual 问题自动联网,联网需用户显式选择;选外部模式时本地知识库完全不参与(纯外部来源回答)。
- **不入库**:小红书结果与 Web 结果同语义 —— 仅本轮可见,不写 Milvus,不影响幂等入库。
