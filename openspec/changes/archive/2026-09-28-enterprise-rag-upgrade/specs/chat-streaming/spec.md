# Spec Delta

## Purpose

慢模型(如 agnes-3.0-flash)下检索前有多次 LLM 串行调用,首字前 40s+ 只见静态"检索中…"会被误认为卡死;同时参考来源块原先渲染在答案上方、且全量罗列(最多 10 条),信息噪声大。本次:① SSE 新增 `status` 阶段事件,前端实时展示"理解 → 召回 → 重排 → 生成"进度;② 参考来源块移到答案之后,最多展示 top3;③ 寒暄/闲聊意图跳过知识库检索直接对话(详见 `langgraph-orchestration` 规格),不产生来源与置信度。

## MODIFIED Requirements

### Requirement: 流式问答接口

系统 SHALL 提供 `POST /chat/stream` 接口,请求体与 `POST /chat` 相同(`{question, session_id}`),响应为 `text/event-stream`,逐事件推送 JSON:SSE 事件顺序 SHALL 为 若干 `status` → `meta` → `status`(生成阶段)→ 若干 `delta` → `done`;生成或检索任一阶段发生不可恢复错误时推送 `error` 事件并结束流。

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

### Requirement: 首页流式渲染

首页提问 SHALL 改走流式接口:发送后先显示检索占位;`status` 事件到达即更新占位文案(阶段进度,保持流式动画);`meta` 事件到达渲染低置信度提示(若触发)并把来源块暂存;`done` 事件定格答案后,把参考来源块(**最多 top3**,重排序后前 3 条即全局最相关)与调试 meta 追加到答案末尾;历史回显渲染路径 SHALL 保持不变。

#### Scenario: 发送后即时反馈
- **WHEN** 用户提交问题
- **THEN** 界面立即出现检索中提示,随 `status` 事件滚动更新阶段文案,无长时间空白

#### Scenario: 答案逐字出现
- **WHEN** 流推送 `delta` 事件
- **THEN** 助手消息气泡内答案文本随事件增量追加并自动滚动到底;`status` 在首个 `delta` 之后不再覆盖答案区

#### Scenario: 来源块置于答案之后且最多 3 条
- **WHEN** `done` 事件到达且 meta 携带来源
- **THEN** 参考来源块渲染在完整答案下方,条数 ≤ 3(取 sources 前 3 条);`error` 收场时来源块同样追加(检索本身是有效信息)

#### Scenario: 闲聊直达对话
- **WHEN** 意图识别为 `chitchat`
- **THEN** 阶段文案显示"闲聊寒暄,跳过知识库检索…",答案直接生成(无来源块、无低置信度提示)
