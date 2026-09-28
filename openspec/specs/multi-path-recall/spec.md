# multi-path-recall

> 从 OpenSpec 变更 `enterprise-rag-upgrade` 同步而来。

## Purpose

查询图在向量召回之外,再引入「HyDE 假设性文档检索」与「MCP Web 搜索」两路召回;三路结果由 RRF 倒数排名融合统一排序后,送入重排节点。HyDE 由意图条件触发,Web 搜索由 `factual` 意图与「启用网络标志」共同决定;MCP 自建 server 暴露 `web_search` 工具,以 stdio 传输由 LangGraph 节点内调用。

## Requirements

### Requirement: HyDE 假设文档生成

系统 SHALL 由 `hyde_search` 节点调用 `LLMClient` 生成一段「假设性回答」(50~200 字),模板提示为 "假设你是该领域专家,直接给出该问题的可能答案(无需真实检索)";HyDE 仅在 `intent in {factual, explanatory}` 时挂载到图中,`chitchat / creative` 时不入图。

#### Scenario: factual 触发 HyDE
- **WHEN** 意图为 `factual`
- **THEN** 查询图多一条 `preprocess → hyde_search` 边,`hyde_search` 节点被调度

#### Scenario: chitchat 不触发 HyDE
- **WHEN** 意图为 `chitchat`
- **THEN** `hyde_search` 节点不入图,日志不出现 `--- hyde_search 开始 ---`

#### Scenario: HyDE 文档拼接
- **WHEN** `hyde_search` 拿到 LLM 输出的 `hyde_doc`
- **THEN** `combined_query = rewritten_query + " " + hyde_doc`,走与 `embedding_search` 相同的 `milvus_hybrid.hybrid_search(...)`,**不复用独立索引**

### Requirement: Web 搜索 MCP 工具

系统 SHALL 提供 `mcp_server/server.py`,通过 Python MCP SDK **2.x**(`mcp.server.mcpserver.MCPServer` + `@server.tool()` 装饰器,函数签名类型注解自动生成 schema)注册 `web_search` 工具,以 Brave Search API(`https://api.search.brave.com/res/v1/web/search`,`X-Subscription-Token` 头)为后端;工具输入为 `{query: str, count: int = 5}`,返回值为 `[{title, url, snippet}, ...]` 的 JSON 字符串(由 SDK 包成 `TextContent`)。升降级 SDK 时注意 v1 的 `Server` + `@server.list_tools()` API 已移除。

#### Scenario: server 注册工具
- **WHEN** `python -m mcp_server` 启动
- **THEN** MCP 客户端 `list_tools()` 至少返回 `web_search`,schema 含 `query` 必填与 `count` 可选

#### Scenario: server 转发 Brave
- **WHEN** 调用 `web_search(query="<q>", count=5)`
- **THEN** server 向 Brave API 发 GET,返回最多 5 条 `{title, url, snippet}`,输出为 `TextContent` 列表

#### Scenario: API Key 缺失
- **WHEN** `BRAVE_SEARCH_API_KEY` 环境变量为空
- **THEN** server 启动仍成功,但首次 `web_search` 调用返回 `TextContent("BRAVE_SEARCH_API_KEY not configured")`,不抛未捕获异常

### Requirement: Web 搜索节点

系统 SHALL 由 `web_search` 节点通过 stdio 传输拉起 `python -m mcp_server` 进程(同一服务进程内,避免另起 HTTP 端口),建立 `ClientSession` 后 `call_tool("web_search", {"query": ..., "count": 5})`;`web_search` 节点仅在 `intent == "factual"` 且 `web_search_enabled == True` 时挂载到图中。

#### Scenario: stdio 拉起
- **WHEN** `web_search` 节点首次执行
- **THEN** 进程内启动 `python -m mcp_server` 子进程,通过 stdio 与其通信,无 8765 端口监听

#### Scenario: factual + 启用 Web
- **WHEN** `intent == "factual"` 且 `web_search_enabled == True`
- **THEN** `web_search` 节点入图,返回结果进入 `web_search_docs`

#### Scenario: Web 关闭标志
- **WHEN** `Config.WEB_SEARCH_ENABLED == False`
- **THEN** 无论意图,`web_search` 节点不入图,日志不出现 web 召回

### Requirement: RRF 倒数排名融合

系统 SHALL 由 `rrf_fuse` 节点对 `embedding_chunks / hyde_embedding_chunks / web_search_docs` 三路结果做 RRF 倒数排名融合:每路用等权 `weight=1.0`,公式 `score[doc_id] += weight / (k + rank)`,`k = 60`;同一文档出现在多路时累加得分;输出按最终得分降序的 `rrf_chunks`。

#### Scenario: 三路等权融合
- **WHEN** 三路各有 10 条
- **THEN** 同时出现在三路的文档得分 = `1/(60+rank_emb) + 1/(60+rank_hyde) + 1/(60+rank_web)`,按得分降序排列

#### Scenario: 单路或多路缺失
- **WHEN** `hyde_embedding_chunks` 为空或 `web_search_docs` 为空
- **THEN** 仅对非空路执行 RRF,空路跳过;不报错

#### Scenario: k 与权重
- **WHEN** `RRF_K` 或 `RRF_WEIGHTS` 从 `Config` 读取
- **THEN** 默认值分别为 `60` 与 `{"embedding": 1.0, "hyde": 1.0, "web": 1.0}`,可在 `.env` 覆盖

### Requirement: Web 结果仅本轮可见

Web 搜索结果 SHALL **不写入 Milvus**,不进入下一轮 RRF / 重排;仅作为本次回答 `sources` 数组的一次性来源,与向量库召回的 sources 字段结构一致(`{text, doc_name, file_dir, chunk_idx, score, source_type}`),`source_type` 取值 `"web"`。

#### Scenario: Web 来源标记
- **WHEN** Web 召回结果进入 `sources`
- **THEN** 每条 hit 的 `source_type == "web"`,前端引用弹层可据此区分

#### Scenario: Web 不入库
- **WHEN** Web 节点返回结果
- **THEN** 不调用 `milvus_hybrid.insert(...)`,Milvus 集合数量不变
