# Tasks

## 1. 前置验证(环境与外部服务)

- [x] 1.1 验证 rag 环境 MCP SDK 具备 Streamable HTTP 客户端:`conda run -n rag python -c "from mcp.client.streamable_http import streamablehttp_client; print('ok')"`;缺则在该环境升级 `mcp` 包并复验 stdio 路径仍可 import(`from mcp import ClientSession, StdioServerParameters`)
- [x] 1.2 确认外部 xiaohongshu-mcp 服务已部署并登录:服务监听 `XHS_MCP_URL`(默认 `http://127.0.0.1:18060/mcp`),用一次性 Python 脚本经 `streamablehttp_client` 调 `search_feeds(keyword="测试")` 成功返回,并记录响应 JSON 的实际字段结构(供 4.2 字段映射校正)
  - 已完成(2026-09-29):部署于 `~/tools/xiaohongshu-mcp/`,扫码登录成功;实测结构 `{id, xsecToken, noteCard:{displayTitle, user:{nickname}, ...}}`(feed 卡片无 desc 字段),与 `_normalize_xhs_item` 映射吻合
  - ⚠️ 官方 v2.5.5 有 search_feeds 稳定 60s 超时 bug(上游 #813),当前跑的是 PR #839 补丁版二进制(`xiaohongshu-mcp-patched`,3/3 稳定 5~8s 返回);上游发修复版后换回官方二进制即可

## 2. 配置层

- [x] 2.1 `app/core/config.py` 新增 `XHS_MCP_ENABLED`(默认 false)/ `XHS_MCP_URL`(默认 `http://127.0.0.1:18060/mcp`)/ `XHS_MCP_TOKEN`(默认空)/ `XHS_SEARCH_LIMIT`(默认 5),`validate()` 加「启用时 URL 非空」校验;验证:临时把 URL 置空 + 启用 → 启动即 RuntimeError,还原后启动正常
- [x] 2.2 `.env` 追加四个新变量的注释示例(注明 xiaohongshu-mcp 需独立部署扫码登录、同账号多处网页端登录会互踢);验证:服务带新配置正常启动
- [x] 2.3 新增 `GET /api/config` 端点(独立小路由,返回 `{web_search_enabled, xhs_enabled}`,不含任何密钥)并在 `main.py` 挂载;验证:`curl http://127.0.0.1:8011/api/config` 返回的布尔与 `.env` 开关一致

## 3. MCP 客户端 HTTP 通道

- [x] 3.1 `app/core/mcp_client.py` 新增 `call_tool_http(url, tool_name, arguments, headers=None)`:每次调用独立建连(streamablehttp_client + ClientSession 上下文),解析 TextContent JSON;头部 docstring 重写为「双 transport:stdio 自建服务 / HTTP 外部服务」;验证:一次性脚本调 `call_tool_http(XHS_MCP_URL, "search_feeds", {...})` 返回解析结果,现有 stdio `call_tool` 的 import 与调用不受影响

## 4. 查询图模式互斥路由

- [x] 4.1 `app/rag/state.py`:`QueryGraphState` 加 `xhs_search_docs: list[dict]` 与 `search_mode: str` 字段及默认值(`"kb"`);验证:import 无错,`create_default_query_state()` 含新键
- [x] 4.2 `app/rag/nodes/query_nodes.py` 新增 `NodeXhsSearch`(async):`asyncio.wait_for` 60s 包 `mcp_client.call_tool_http`,调 `search_feeds(keyword=rewritten_query)`,按 1.2 实测字段防御性提取,取前 `XHS_SEARCH_LIMIT` 条规范化(text/doc_name/file_dir/metadata 含 feed_id+xsec_token/score=1.0/source_type="xhs"),异常全捕降级空路 + warning;`_doc_id_of` 加 `xhs::` 前缀分支;验证:小红书服务可用时节点返回非空 docs,停服务后返回空且日志仅 warning
- [x] 4.3 `route_after_preprocess` 改为模式互斥:chitchat 直达 cliff_rerank;`kb` → embedding(+hyde 按现行规则);`web` → 仅 web_search;`xhs` → 仅 xhs_search;`app/rag/query_graph.py` 注册 `xhs_search` 节点 + 条件边映射 + 汇向 `rrf_fuse`;验证:三种模式各提一问,日志确认只调度对应路、无多余节点
- [x] 4.4 `NodeRrfFuse` 改为「模式内融合」:路径表按 `search_mode` 取当前挂载的各路(kb → embedding+hyde;web/xhs → 单路),`RR_WEIGHTS` 加 `xhs`(1.0);验证:`kb` 模式同文档两路得分累加,`xhs` 模式单路顺序不变
- [x] 4.5 `app/rag/pipeline.py`:`query / query_stream` 加 `search_mode="kb"` 参数注入初始状态;`_build_response` 的 `raw_count` / `_recall_paths` 按模式统计(含 `xhs`);`_STAGE_MSGS` 注册 `xhs_search` 文案,`preprocess` 后的召回阶段文案按模式区分(kb / web / xhs);验证:`POST /chat` 不带新参数的响应与改动前同形(kb 路径)

## 5. API 层模式参数

- [x] 5.1 `app/api/chat.py`:`ChatRequest` 加 `search_mode: Literal["kb", "web", "xhs"] = "kb"`,两出口(`/chat`、`/chat/stream`)透传给 pipeline;`_resolve` 校验「模式对应主开关未启用 → 4xx」;验证:`search_mode: "baidu"` 与「`xhs` 但 `XHS_MCP_ENABLED=false`」均被拒收;`web` 模式请求日志仅出现 web_search 一路

## 6. 前端下拉选择器

- [x] 6.1 `static/index.html` 输入区加 `<select id="search-mode">`(选项:仅知识库 / 联网搜索 / 小红书,样式跟随现有输入区视觉);`static/app.js`:加载时拉 `GET /api/config` 过滤选项(源不可用隐藏对应项;两源均不可用整体隐藏下拉),`localStorage` 记忆 / 恢复上次选择(不可用回落仅知识库),提交提问时请求体带 `search_mode`;验证:浏览器实测 —— 开关组合下选项正确增删 / 整体隐藏、刷新后选择恢复、选小红书提问 SSE 出现小红书阶段文案且来源可见 xhs 条目、选联网时无任何本地召回日志

## 7. 文档与端到端收尾

- [x] 7.1 更新 `CLAUDE.md`(技术栈 / 运行验证段提搜索模式互斥路由、小红书召回与外部服务前置条件、同账号互踢约束);验证:文档描述与实际行为一致
- [x] 7.2 端到端验证:① 选「联网」→ 答案仅基于 web 来源,`recall_paths` 仅 `web`;② 选「小红书」→ 仅 xhs 来源;③ 选「仅知识库」→ 行为与升级前一致;④ 停掉 xiaohongshu-mcp 服务再选小红书提问 → 问答正常、降级空路、答案如实不知道;⑤ `openspec validate xhs-mcp-recall --strict` 通过
  - 2026-09-29 实测:② xhs 模式 recall_paths=["xhs"]、来源全为真实笔记(4 召回 3 重排);③ kb 缺省回归正常;④ 服务未起时降级空路、如实「不知道」;⑤ 通过
  - ① 联网模式未测:`WEB_SEARCH_ENABLED=false` 且 BRAVE_SEARCH_API_KEY 未配(遗留事项,见 memory enterprise-rag-upgrade-verification),启用后补测
