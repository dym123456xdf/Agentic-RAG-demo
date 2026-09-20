# Proposal

## Why

首页提问从"发送"到"看到答案"要串行等完 预处理(3 次 LLM)→ 召回 → BGE 重排(冷启 ~13s)→ 生成,前端阻塞 fetch 收全量 JSON,中途黑屏,体感等待 20s+。同时来源列表只展示 BGE 原始 logit(约 -10~10 无界),没有 0-1 可比的置信度,用户无法判断答案可信度。

## What Changes

- 新增流式问答接口 `POST /chat/stream`(SSE):先推 `meta` 事件(召回+重排完成即推,含来源与逐文档置信度),再逐块推 `delta` 答案增量,末推 `done`(含答案全文);生成阶段任一点异常推 `error`。原有 `POST /chat` 保留不动。
- 答案来源增加 0-1 置信度:`confidence = sigmoid(BGE 原始分)`(0.6 对应 logit≈0.41);`meta` 同时带整体置信度(取 top1)。
- 前端首页改走流式:meta 到达即渲染参考来源块(感知提速),答案逐字输出;历史回显渲染路径不变。
- 低置信度友情提示:top1 置信度 < 0.6 时,参考来源块上方显示一条软提示("参考置信度偏低,答案可能不够可靠,建议核对原文档"),文案内带具体数值;阈值 0.6 可经 `.env` `CONFIDENCE_THRESHOLD` 调整。
- 生成器支持流式输出,并在流上过滤 M3 的 `think` 推理块(部分流安全过滤,已闭合的块剥除、未闭合的尾部滞留缓冲)。

## Capabilities

### New Capabilities

- `chat-streaming`: 流式问答接口的 SSE 事件契约(meta/delta/done/error)、答案来源 0-1 置信度展示、低置信度(<0.6)友情提示,以及首页流式渲染行为。

### Modified Capabilities

- `chat-sessions`: "聊天请求绑定会话" 要求中的响应结构来源列表新增 `confidence` 字段(原 logit `score` 字段保留,不删除);历史持久化的来源/meta JSON 因此携带置信度,其余行为不变。

## Impact

- **代码**: `app/rag/generator.py`(流式生成 + think 过滤)、`app/rag/pipeline.py`(query_stream)、`app/rag/post.py`(重排分转 0-1 置信度)、`app/api/chat.py`(新增 `/chat/stream` 路由,meta 事件含置信度;落库 sources 带 confidence)、`app/core/config.py`(CONFIDENCE_THRESHOLD)、`static/index.html` + `static/app.js`(流式 fetch + 来源块/提示渲染)。
- **API**: 新增 `POST /chat/stream`(`text/event-stream`);`POST /chat` 响应 sources 每项新增 `confidence: float | None`(纯新增,旧客户端不受影响;值为 null 表示该节点未经过重排,前端隐藏)。
- **数据**: MySQL messages 的 sources/meta JSON 列自动带新字段,无需迁移;旧历史记录无 confidence 字段,前端渲染需容错(缺字段不显示提示、不显示数值)。
- **不受影响**: 检索/重排链路、入库链路、管理页历史回溯(仍走非流式展示)、会话管理。
