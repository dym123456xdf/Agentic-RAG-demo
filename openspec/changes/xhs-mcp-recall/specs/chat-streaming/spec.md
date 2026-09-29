# Spec Delta

## MODIFIED Requirements

### Requirement: 流式问答接口

系统 SHALL 提供 `POST /chat/stream` 接口,请求体与 `POST /chat` 相同(`{question, session_id, search_mode}`,`search_mode` 为可选的搜索模式选择,见 `search-mode-selection` 能力),响应为 `text/event-stream`,逐事件推送 JSON:SSE 事件顺序 SHALL 为 若干 `status` → `meta` → `status`(生成阶段)→ 若干 `delta` → `done`;生成或检索任一阶段发生不可恢复错误时推送 `error` 事件并结束流。

`status` 事件载荷为 `{type: "status", text: str}`,text 为当前阶段的人类可读文案(如"理解问题中(改写 + 意图识别)…"、"多路召回中(向量 + HyDE)…"、"重排打分中…"、"生成答案中…"、"闲聊寒暄,跳过知识库检索…");文案由服务端决定,前端只负责展示。

#### Scenario: 检索完成先推 meta
- **WHEN** 服务端完成查询预处理、检索与重排(尚未开始生成答案)
- **THEN** 流中先推送一条 `meta` 事件,携带来源列表(含各条置信度)与调试 meta,早于任何答案文本

#### Scenario: 阶段进度实时可见
- **WHEN** 检索图的任一节点(preprocess / 各路召回 / rrf_fuse)完成
- **THEN** 对应 `status` 事件即被推送,前端占位文案随之更新,不再长时间停留在静态"检索中…"

#### Scenario: 答案逐块推送
- **WHEN** 答案生成进行中
- **THEN** 每产出一段答案文本即推送一条 `delta` 事件,前端可据此增量渲染

#### Scenario: 流正常结束
- **WHEN** 答案生成完毕
- **THEN** 流最后推送 `done` 事件,携带完整答案文本,该问答对(问题、答案、来源、meta)按非流式接口同一规则落库

#### Scenario: 流中出错
- **WHEN** 生成阶段发生异常(模型超时等)
- **THEN** 流推送 `error` 事件(含错误说明)并结束,不推送 `done`,不产生误导性落库

#### Scenario: 请求携带搜索模式
- **WHEN** 请求体携带 `search_mode: "xhs"`
- **THEN** 该模式透传到查询图,仅小红书路挂载;流式事件序列与不带该字段时结构一致
