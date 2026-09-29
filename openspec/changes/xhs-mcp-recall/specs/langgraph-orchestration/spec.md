# Spec Delta

## ADDED Requirements

### Requirement: 查询图模式路由装配

系统 SHALL 在 `app/rag/query_graph.py` 装配两个编译产物:`RETRIEVAL_GRAPH`(preprocess → 按搜索模式互斥路由:`kb` 挂载 `embedding_search`(及按意图规则的 `hyde_search`),`web` 仅挂载 `web_search`,`xhs` 仅挂载 `xhs_search`;挂载路均汇向 `rrf_fuse` → `cliff_rerank` → END,不含 generate,流式出口用)与 `QUERY_GRAPH`(RETRIEVAL_GRAPH 之后接 `generate` 节点,非流式整图);条件路由由 `route_after_preprocess` 依据 `search_mode`(见 `search-mode-selection` 能力)+ 意图 + 开关决定,`chitchat`(寒暄/闲聊)意图 SHALL 直达 `cliff_rerank`(空跑 no-op),跳过全部召回;`app/rag/pipeline.py` 暴露 `query(question, history, session_id, message_id)` 与 `query_stream(question, history, session_id, message_id)`。

#### Scenario: kb 模式两路召回
- **WHEN** `search_mode == "kb"`、意图为 `factual` 且 HyDE 启用
- **THEN** `embedding_search` 与 `hyde_search` 同时被调度,两路结果均进入 `rrf_fuse`(可在日志中看到两路几乎同时开始)

#### Scenario: web 模式单路
- **WHEN** `search_mode == "web"` 且 `WEB_SEARCH_ENABLED == True`
- **THEN** 仅 `web_search` 被调度,`embedding_search` / `hyde_search` / `xhs_search` 均不入图

#### Scenario: xhs 模式单路
- **WHEN** `search_mode == "xhs"` 且 `XHS_MCP_ENABLED == True`(意图为任意非 `chitchat`)
- **THEN** 仅 `xhs_search` 被调度,其余召回路均不入图

#### Scenario: chitchat 跳过知识库检索
- **WHEN** 查询意图为 `chitchat`(如"你好"、"在吗"),无论何种搜索模式
- **THEN** `embedding_search` / `hyde_search` / `web_search` / `xhs_search` 均不执行(日志无对应节点),直达 `cliff_rerank`(空输入 no-op),`generate` 走闲聊分支:以 `build_chitchat_messages`(带最近历史、无参考资料约束)直接生成自然回应,不出现"我不知道,资料里没提到"兜底,meta 无来源与置信度

#### Scenario: creative 在 kb 模式仅走向量
- **WHEN** `search_mode == "kb"` 且查询意图为 `creative`
- **THEN** `hyde_search` 不执行,仅 `embedding_search` 单独召回;外部模式不受意图约束(用户显式选择优先)

## REMOVED Requirements

### Requirement: 查询图装配
**Reason**: 多路并行扇出(向量 / HyDE / Web 三路同时调度)改为搜索模式互斥路由,原装配描述与场景不再成立。
**Migration**: 由「查询图模式路由装配」取代 —— 图结构、汇合节点与两个编译产物(RETRIEVAL_GRAPH / QUERY_GRAPH)保持不变,仅条件路由的决策依据变为搜索模式 + 意图 + 开关。
