# langgraph-orchestration Specification

## Purpose

把入库与查询两条业务流迁移到 LangGraph `StateGraph` 上,以 TypedDict 状态契约为单一数据载体,业务拆成可独立替换、可观测、可单测的节点(`BaseNode` 基类 + `process()` 抽象),并由 `app/rag/pipeline.py` 暴露为统一的 `query / query_stream / ingest` 入口;既保留现有 `LLMClient`(llama-index `OpenAILike`)与 MySQL 持久化,又获得 LangGraph 的状态化编排能力。

## ADDED Requirements

### Requirement: 节点基类 `BaseNode`

系统 SHALL 提供 `app/rag/base.py` 中的 `BaseNode(ABC)`,所有入库与查询节点必须继承该基类,实现 `name: str` 与 `flow: str`("ingest"/"query")类属性与 `process(state) -> state` 抽象方法;基类 `__call__(state)` 统一封装日志、异常包装,日志前缀分别为 `ingest.<name>` 与 `query.<name>`;子类 `process` 为 `async def` 时基类自动走异步包装(供 MCP stdio 等 await 场景),LangGraph 对 sync/async 节点均原生支持。

#### Scenario: 基类封装日志
- **WHEN** 任意节点被 LangGraph 调用
- **THEN** 进入日志打印 `--- <name> 开始 ---`,正常完成打印 `--- <name> 完成 ---`,异常时打印 `<name> 失败: <err>` 并抛出自定义异常(`IngestProcessError` / `QueryProcessError`)

#### Scenario: 异常不静默吞掉
- **WHEN** `process()` 抛任意异常
- **THEN** 由 `__call__` 包装后重新抛出,LangGraph 能捕获并停止图执行,不返回半成品状态

### Requirement: 入库图装配

系统 SHALL 在 `app/rag/ingest_graph.py` 装配入库 `StateGraph`,节点顺序固定为 `entry → pdf_to_md → md_img → doc_split → item_name_recognition → bge_embedding → import_milvus`,入口点为 `entry`,终点为 `END`;`app/rag/pipeline.py` 暴露 `ingest(task_id, file_path)` 调用 `INGEST_GRAPH.ainvoke(state)`。

#### Scenario: 入库链路完整执行
- **WHEN** 上传一份 PDF 触发入库图
- **THEN** 7 个节点按上述顺序依次执行,每个节点产出日志,最终 Milvus 中可见该文件 chunk

#### Scenario: 任何节点失败立即停止
- **WHEN** `pdf_to_md` 节点抛 `RuntimeError`(MinerU 转换失败)
- **THEN** 图执行立即停止,不进入后续节点,不写入半成品 chunk 到 Milvus

### Requirement: 查询图装配

系统 SHALL 在 `app/rag/query_graph.py` 装配两个编译产物:`RETRIEVAL_GRAPH`(preprocess → 按意图条件路由到 `embedding_search` / `hyde_search` / `web_search` 三路并行,各路均汇向 `rrf_fuse` → `cliff_rerank` → END,不含 generate,流式出口用)与 `QUERY_GRAPH`(RETRIEVAL_GRAPH 之后接 `generate` 节点,非流式整图);条件路由由 `route_after_preprocess` 决定,`chitchat`(寒暄/闲聊)意图 SHALL 直达 `cliff_rerank`(空跑 no-op),跳过全部召回;`app/rag/pipeline.py` 暴露 `query(question, history, session_id, message_id)` 与 `query_stream(question, history, session_id, message_id)`。

#### Scenario: 三路并行召回
- **WHEN** 查询图为 `factual` 意图且 HyDE / Web 均启用
- **THEN** `embedding_search`、`hyde_search`、`web_search` 同时被调度,三路结果均进入 `rrf_fuse`(可在日志中看到三路几乎同时开始)

#### Scenario: chitchat 跳过知识库检索
- **WHEN** 查询意图为 `chitchat`(如"你好"、"在吗")
- **THEN** `embedding_search` / `hyde_search` / `web_search` 均不执行(日志无对应节点),直达 `cliff_rerank`(空输入 no-op),`generate` 走闲聊分支:以 `build_chitchat_messages`(带最近历史、无参考资料约束)直接生成自然回应,不出现"我不知道,资料里没提到"兜底,meta 无来源与置信度

#### Scenario: creative 跳过 HyDE 与 Web
- **WHEN** 查询意图为 `creative`
- **THEN** `hyde_search` 与 `web_search` 节点不执行,仅 `embedding_search` 单独召回

### Requirement: 状态契约

系统 SHALL 定义两个 TypedDict 状态 `ImportGraphState` 与 `QueryGraphState`(`total=False`,所有字段可选,缺失字段在节点内部兜底),并由 `create_default_import_state(**overrides)` 与 `create_default_query_state(**overrides)` 工厂返回新对象(深拷贝默认),避免全局状态污染。

#### Scenario: 默认状态字段齐全
- **WHEN** 任一节点被调用
- **THEN** 状态中缺失字段视为空值或空列表,节点逻辑不因字段缺失崩溃

#### Scenario: 工厂返回独立副本
- **WHEN** 两次调用 `create_default_query_state()`
- **THEN** 返回的两个 state 是不同对象,修改其一不影响另一个

### Requirement: LLM 客户端保留

系统 SHALL 保留 `app/core/llm.py` 中的 `LLMClient`(llama-index `OpenAILike` + `strip_thinking` + `ThinkStreamFilter`),节点内部直接 `await self.llm.achat(...)` 或同步 `self.llm.chat(...)`;**不引入 LangChain `ChatOpenAI`**。

#### Scenario: 节点内复用 LLMClient
- **WHEN** `generate` / `item_name_recognition` / `hyde_search` 节点需要调用 LLM
- **THEN** 通过注入的 `LLMClient` 实例完成,代码不出现 `from langchain.chat_models import ChatOpenAI`

#### Scenario: 流式过滤仍生效
- **WHEN** 流式生成 token 经过 `generate` 节点
- **THEN** `ThinkStreamFilter` 仍剥离 `<think>` 块,前端 SSE 只收到回答正文

### Requirement: 管线入口契约

系统 SHALL 由 `app/rag/pipeline.py` 暴露三个顶层入口函数:`ingest(task_id, file_path)`(异步入库)、`query(question, history, ...)`(非流式查询,返回 `{answer, sources, meta}`)、`query_stream(question, history, ...)`(同步生成器,逐事件 yield `(event, payload)` 元组);FastAPI 路由 `app/api/upload.py`、`app/api/chat.py` SHALL 仅调用这三个入口,不直接接触 LangGraph。

#### Scenario: 流式两段实现
- **WHEN** `query_stream` 被调用
- **THEN** 第一段以 `astream(stream_mode="updates")` 驱动 `RETRIEVAL_GRAPH`,检索图每完成一个节点即 yield 一条 `status` 事件(阶段提示),子图终态由各节点增量按序 merge 得到;第二段在图外用 `LLMClient.stream_chat` + `ThinkStreamFilter` 逐块 yield `delta`,`done` 携带完整答案(llama-index LLM 不发 LangChain 事件,`astream_events` 拿不到 token 级增量,故 generate 节点只服务非流式路径)

#### Scenario: 同步生成器的异步桥接
- **WHEN** SSE 的 `event_stream()` 在 FastAPI 线程池里迭代 `query_stream`(无事件循环)
- **THEN** 检索子图的异步推进由后台线程跑 `asyncio.run` + `queue` 桥接回同步生成器,`status` 事件实时产出

#### Scenario: 路由层无 LangGraph 依赖
- **WHEN** 检查 `app/api/upload.py` 与 `app/api/chat.py` 的 import
- **THEN** 不出现 `from langgraph import ...`,LangGraph 仅在 `app/rag/*` 模块内出现
