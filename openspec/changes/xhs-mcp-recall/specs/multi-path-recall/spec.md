# Spec Delta

## ADDED Requirements

### Requirement: MCP HTTP transport 客户端

系统 SHALL 在 MCP 客户端支持 Streamable HTTP 传输:按配置的 URL 建立到外部 MCP 服务的连接,完成初始化握手后调用指定工具,并将 `TextContent` 的 JSON 输出解析为结构化结果;配置了访问令牌时 SHALL 携带 `Authorization: Bearer <token>` 请求头。每次调用独立建连,不在服务进程内维持长连接会话。既有 stdio 传输(自建 Brave server)SHALL 保持不变。

#### Scenario: HTTP 调用外部工具
- **WHEN** 以 HTTP 传输调用外部 MCP 服务的某工具且服务可达
- **THEN** 客户端完成 MCP 初始化握手后调用该工具,返回值为 TextContent JSON 的解析结果

#### Scenario: 令牌鉴权
- **WHEN** 配置了 MCP 访问令牌
- **THEN** 每次请求携带 `Authorization: Bearer <token>` 头;未配置时不携带该头

#### Scenario: stdio 路径不受影响
- **WHEN** Web 搜索节点经 stdio 拉起自建 mcp_server
- **THEN** 行为与接入 HTTP 传输前完全一致

### Requirement: 小红书 MCP 召回节点

系统 SHALL 提供 `xhs_search` 节点,以 HTTP 传输调用外部部署的小红书 MCP 服务(xiaohongshu-mcp)的 `search_feeds` 工具,入参 `{keyword: 改写后查询}`;取返回笔记列表前 `XHS_SEARCH_LIMIT` 条(默认 5),规范化为与 Web 召回同形的文档:`{text(标题+摘要), doc_name(标题), file_dir(笔记链接), chunk_idx: 0, score: 1.0, source_type: "xhs"}`。节点仅在搜索模式为小红书(`search_mode == "xhs"`,见 `search-mode-selection` 能力)且 `XHS_MCP_ENABLED == True` 时挂载到图中,与查询意图无关(`chitchat` 除外,仍跳过全部召回);该模式下本地向量 / HyDE 召回均不执行。调用 SHALL 受 60 秒超时上限约束。

#### Scenario: 选择小红书模式 + 主开关启用
- **WHEN** 用户请求的 `search_mode == "xhs"` 且 `XHS_MCP_ENABLED == True`
- **THEN** `xhs_search` 节点入图且是唯一召回路,结果进入 `xhs_search_docs`,每条 `source_type == "xhs"`

#### Scenario: 未选或主开关关闭
- **WHEN** `search_mode != "xhs"` 或 `XHS_MCP_ENABLED == False`
- **THEN** `xhs_search` 节点不入图,日志不出现小红书召回;主开关关闭时 `xhs` 模式请求被 4xx 拒收

#### Scenario: 服务不可达降级
- **WHEN** 小红书 MCP 服务未启动、登录态失效、调用超过 60 秒或响应解析失败
- **THEN** 该路返回空列表并记 warning 日志,查询流程不中断,按空召回继续走重排与生成

#### Scenario: 启用校验
- **WHEN** `XHS_MCP_ENABLED == True` 且 `XHS_MCP_URL` 为空
- **THEN** 服务启动即失败(快速失败);除此之外启动期不对小红书服务做网络探测

### Requirement: 小红书结果仅本轮可见

小红书召回结果 SHALL 不写入 Milvus,不进入下一轮检索;仅作为本次回答 `sources` 的一次性来源,结构与向量 / Web 来源一致;文档去重标识使用 `xhs::<笔记链接>` 前缀。

#### Scenario: 小红书不入库
- **WHEN** `xhs_search` 节点返回结果
- **THEN** 不调用 Milvus 写入,集合数量不变

#### Scenario: 来源标记区分
- **WHEN** 小红书召回结果进入 `sources`
- **THEN** 每条 `source_type == "xhs"`,与 `"web"` / `"vector"` 可区分

### Requirement: RRF 模式内融合

系统 SHALL 由 `rrf_fuse` 节点对「当前搜索模式下挂载的各路召回结果」做 RRF 倒数排名融合:`kb` 模式融合 `embedding_chunks / hyde_embedding_chunks`(至多两路),`web` 模式仅 `web_search_docs`,`xhs` 模式仅 `xhs_search_docs`;每路用等权 `weight=1.0`,公式 `score[doc_id] += weight / (k + rank)`,`k = 60`;同一文档出现在多路时累加得分;输出按最终得分降序的 `rrf_chunks`。

#### Scenario: kb 模式两路融合
- **WHEN** `kb` 模式下向量与 HyDE 两路各有结果
- **THEN** 同时出现在两路的文档得分 = `1/(60+rank_emb) + 1/(60+rank_hyde)`,按得分降序排列

#### Scenario: 单路模式退化
- **WHEN** `search_mode == "web"`(或 `"xhs"`)仅一路有结果
- **THEN** RRF 对该路单独执行,排序等价于按该路原顺序的重排,不报错

#### Scenario: 模式内某路为空
- **WHEN** `kb` 模式下 `hyde_embedding_chunks` 为空
- **THEN** 仅对非空路执行 RRF,空路跳过;不报错

#### Scenario: k 与权重
- **WHEN** `RRF_K` 或 `RRF_WEIGHTS` 从 `Config` 读取
- **THEN** 默认值分别为 `60` 与 `{"embedding": 1.0, "hyde": 1.0, "web": 1.0, "xhs": 1.0}`,可在 `.env` 覆盖

## MODIFIED Requirements

### Requirement: HyDE 假设文档生成

系统 SHALL 由 `hyde_search` 节点调用 `LLMClient` 生成一段「假设性回答」(50~200 字),模板提示为 "假设你是该领域专家,直接给出该问题的可能答案(无需真实检索)";HyDE 仅在搜索模式为仅知识库(`search_mode == "kb"`,见 `search-mode-selection` 能力)且 `intent in {factual, explanatory}` 时挂载到图中,`chitchat / creative` 时及外部检索模式下不入图。

#### Scenario: factual 触发 HyDE
- **WHEN** 搜索模式为 `kb` 且意图为 `factual`
- **THEN** 查询图多一条 `preprocess → hyde_search` 边,`hyde_search` 节点被调度

#### Scenario: chitchat 不触发 HyDE
- **WHEN** 意图为 `chitchat`
- **THEN** `hyde_search` 节点不入图,日志不出现 `--- hyde_search 开始 ---`

#### Scenario: HyDE 文档拼接
- **WHEN** `hyde_search` 拿到 LLM 输出的 `hyde_doc`
- **THEN** `combined_query = rewritten_query + " " + hyde_doc`,走与 `embedding_search` 相同的 `milvus_hybrid.hybrid_search(...)`,**不复用独立索引**

### Requirement: Web 搜索节点

系统 SHALL 由 `web_search` 节点通过 stdio 传输拉起 `python -m mcp_server` 进程(同一服务进程内,避免另起 HTTP 端口),建立 `ClientSession` 后 `call_tool("web_search", {"query": ..., "count": 5})`;`web_search` 节点仅在搜索模式为联网(`search_mode == "web"`,见 `search-mode-selection` 能力)且 `web_search_enabled == True` 时挂载到图中,与查询意图无关(`chitchat` 除外,仍跳过全部召回);该模式下本地向量 / HyDE 召回均不执行。

#### Scenario: stdio 拉起
- **WHEN** `web_search` 节点首次执行
- **THEN** 进程内启动 `python -m mcp_server` 子进程,通过 stdio 与其通信,无 8765 端口监听

#### Scenario: factual + 启用 Web
- **WHEN** 用户请求的 `search_mode == "web"` 且 `web_search_enabled == True`(意图不限,含 `factual`)
- **THEN** `web_search` 节点入图且与本地召回互斥,返回结果进入 `web_search_docs`

#### Scenario: Web 关闭标志
- **WHEN** `Config.WEB_SEARCH_ENABLED == False`
- **THEN** `web_search` 节点不入图,`web` 模式请求被 4xx 拒收;其它模式下日志不出现 web 召回

## REMOVED Requirements

### Requirement: RRF 倒数排名融合
**Reason**: 检索改为搜索模式互斥路由后,向量 / HyDE / Web 三路同时融合不再发生,融合范围需按模式收窄。
**Migration**: 由「RRF 模式内融合」取代 —— 公式与等权语义不变,仅融合对象变为当前搜索模式下挂载的召回路(至多两路)。
