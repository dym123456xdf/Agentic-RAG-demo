# Spec Delta

## Purpose

让首页提问的答案边生成边显示(流式),检索完成即可先看到参考来源与 0-1 置信度;当主证据置信度低于 0.6 时向用户发出友情提示,降低对不可靠答案的盲信。

## ADDED Requirements

### Requirement: 流式问答接口

系统 SHALL 提供 `POST /chat/stream` 接口,请求体与 `POST /chat` 相同(`{question, session_id}`),响应为 `text/event-stream`,逐事件推送 JSON:SSE 事件顺序 SHALL 为 `meta` → 若干 `delta` → `done`;生成或检索任一阶段发生不可恢复错误时推送 `error` 事件并结束流。

#### Scenario: 检索完成先推 meta

- **WHEN** 服务端完成查询预处理、检索与重排(尚未开始生成答案)
- **THEN** 流中先推送一条 `meta` 事件,携带来源列表(含各条置信度)与调试 meta,早于任何答案文本

#### Scenario: 答案逐块推送

- **WHEN** 答案生成进行中
- **THEN** 每产出一段答案文本即推送一条 `delta` 事件,前端可据此增量渲染

#### Scenario: 流正常结束

- **WHEN** 答案生成完毕
- **THEN** 流最后推送 `done` 事件,携带完整答案文本,该问答对(问题、答案、来源、meta)按非流式接口同一规则落库

#### Scenario: 流中出错

- **WHEN** 生成阶段发生异常(模型超时等)
- **THEN** 流推送 `error` 事件(含错误说明)并结束,不推送 `done`,不产生误导性落库

### Requirement: 答案来源携带 0-1 置信度

来源列表的每一项 SHALL 携带 `confidence` 字段,为 0-1 区间的浮点(由重排模型原始分归一化得出,原始 `score` 字段保留);流式接口的 `meta` 事件与非流式接口 `POST /chat` 的响应来源列表均携带该字段。

#### Scenario: 非流式响应带置信度

- **WHEN** 客户端调用 `POST /chat`
- **THEN** 响应 `sources` 每项含 `confidence`(0-1),原有 `score`(原始分)字段不变

#### Scenario: 旧历史兼容

- **WHEN** 渲染的历史消息来源数据缺少 `confidence` 字段(旧落库记录)
- **THEN** 界面正常渲染,不显示置信度数值、不显示低置信度提示,不报错

### Requirement: 低置信度友情提示

当答案主证据(置信度最高的一条来源)的 `confidence` 低于 0.6 时,界面 SHALL 在参考来源块上方显示一条友情提示,说明参考置信度偏低、答案可能不够可靠并建议核对原文档,提示中呈现该置信度数值;阈值 0.6 SHALL 可经环境变量 `CONFIDENCE_THRESHOLD` 调整。

#### Scenario: 主证据置信度达标

- **WHEN** 最高置信度 ≥ 0.6
- **THEN** 界面不显示友情提示

#### Scenario: 主证据置信度不足

- **WHEN** 最高置信度 0.45,阈值 0.6
- **THEN** 界面在参考来源块上方显示提示,文案包含 0.45 与"建议核对原文档"语义

### Requirement: 首页流式渲染

首页提问 SHALL 改走流式接口:发送后先显示检索中状态,`meta` 事件到达即渲染参考来源块(含逐条置信度),随后答案逐字追加显示;历史回显渲染路径 SHALL 保持不变。

#### Scenario: 发送后即时反馈

- **WHEN** 用户提交问题
- **THEN** 界面立即出现检索中提示,无长时间空白

#### Scenario: 答案逐字出现

- **WHEN** 流推送 `delta` 事件
- **THEN** 助手消息气泡内答案文本随事件增量追加并自动滚动到底
