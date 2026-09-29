# chat-streaming

> 从 OpenSpec 变更 `chat-streaming-confidence` 同步而来。
> 2026-09-28 从 OpenSpec 变更 `enterprise-rag-upgrade` 同步而来。

## Purpose

让首页提问的答案边生成边显示(流式),检索完成即可先看到参考来源与 0-1 置信度;当主证据置信度低于 0.6 时向用户发出友情提示,降低对不可靠答案的盲信。参考来源项同时携带可跳转的原始出处链接(url:知识库 = 转换 MD 代理路径,web / xhs = 原 URL / 笔记链接),来源行在新标签页一键跳出处。

## Requirements

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

### Requirement: 答案来源携带 0-1 置信度

来源列表的每一项 SHALL 携带 `confidence` 字段,为 0-1 区间的浮点(由重排模型原始分归一化得出,原始 `score` 字段保留);流式接口的 `meta` 事件与非流式接口 `POST /chat` 的响应来源列表均携带该字段。

每一项 SHALL 额外携带 `url` 字段(0 或 1 字符串,可为 `null`),为该来源可跳转的原始出处链接:

- `source_type = web`:`url` 为召回时写入的来源 `file_dir`(原网页 URL),缺失时 `null`。
- `source_type = xhs`:`url` SHALL 为可直达笔记页的小红书链接 —— 在召回写入的 `file_dir`(裸笔记链接 `https://www.xiaohongshu.com/explore/<feed_id>`)基础上追加 `?xsec_token=<token>&xsec_source=pc_feed` 查询参数,`token` 取召回时随文档 `metadata` 存储的 `xsec_token`;`xsec_token` 缺失或为空时 SHALL 退回裸笔记链接(不带查询参数);`file_dir` 缺失时 `null`。
- `source_type = vector`(知识库):`url` 按 MinerU 转换产物对象约定拼为相对路径 `/converted/<stem>/<stem>.md`,其中 `stem` = 原文件名(`doc_name`)去后缀;`doc_name` 缺失时 `null`。
- 定位信息缺失(旧数据无 `doc_name` / `file_dir`)一律映射为 `null`,该条不渲染链接。

`url` 随来源落库(JSON 含该 key),历史回溯接口原样返回;带 `xsec_token` 的链接随落库快照固化,系统 SHALL 不对该 token 做时效性检测或回填(过期后的历史链接退化为裸链现状行为)。

#### Scenario: 非流式响应带置信度
- **WHEN** 客户端调用 `POST /chat`
- **THEN** 响应 `sources` 每项含 `confidence`(0-1),原有 `score`(原始分)字段不变

#### Scenario: 非流式响应带跳转链接
- **WHEN** 客户端调用 `POST /chat`
- **THEN** 响应 `sources` 每项含 `url`(字符串或 `null`),定位信息缺失时该条 `url` 为 `null`

#### Scenario: 流式 meta 帧带跳转链接
- **WHEN** 流式接口 `POST /chat/stream` 推送 `meta` 事件
- **THEN** 该事件 `sources` 每项与 `POST /chat` 响应同形(含 `url` 字段),历史落库 JSON 同步携带

#### Scenario: 小红书来源链接直达笔记页
- **WHEN** 任一出口(流式 `meta` 事件 / 非流式响应 / 历史回溯)返回 `source_type = xhs` 且召回 `metadata` 存有 `xsec_token` 的来源
- **THEN** 该条 `url` 形如 `https://www.xiaohongshu.com/explore/<feed_id>?xsec_token=<token>&xsec_source=pc_feed`,浏览器打开能进入对应笔记页,而非「笔记暂时无法浏览」/登录墙

#### Scenario: 小红书令牌缺失降级
- **WHEN** `source_type = xhs` 的来源 `metadata` 中 `xsec_token` 缺失或为空(如上游搜索结果未返回令牌)
- **THEN** 该条 `url` 为裸笔记链接 `https://www.xiaohongshu.com/explore/<feed_id>`(不带查询参数),其余来源不受影响

#### Scenario: 旧历史兼容
- **WHEN** 渲染的历史消息来源数据缺少 `confidence` 或 `url` 字段(旧落库记录)
- **THEN** 界面正常渲染:不显示置信度数值、不显示低置信度提示、来源行保持纯文本不渲染链接,不报错

### Requirement: 低置信度友情提示

当答案主证据(置信度最高的一条来源)的 `confidence` 低于 0.6 时,界面 SHALL 在参考来源块上方显示一条友情提示,说明参考置信度偏低、答案可能不够可靠并建议核对原文档,提示中呈现该置信度数值;阈值 0.6 SHALL 可经环境变量 `CONFIDENCE_THRESHOLD` 调整。

#### Scenario: 主证据置信度达标
- **WHEN** 最高置信度 ≥ 0.6
- **THEN** 界面不显示友情提示

#### Scenario: 主证据置信度不足
- **WHEN** 最高置信度 0.45,阈值 0.6
- **THEN** 界面在参考来源块上方显示提示,文案包含 0.45 与"建议核对原文档"语义

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

### Requirement: 来源行可点击跳转

首页流式渲染与管理页历史回溯共用的来源行 SHALL 在来源项 `url` 非空时,把来源名渲染为可点击跳转链接(新标签页打开,`target="_blank" rel="noopener"`),使读者一键核对原始出处;`url` 为 `null` 或缺失时来源行保持现状纯文本渲染(无链接、无图标、不报错)。跳转链接的视觉表现属 `ui-style` 能力(见其「来源行跳转链接视觉」要求)。

#### Scenario: 有 url 的来源可跳转
- **WHEN** 来源项 `url` 为 `/converted/<stem>/<stem>.md`、web 原 URL 或 xhs 笔记链接
- **THEN** 来源名渲染为带外链图标的链接,点击在新标签页打开该出处,当前会话上下文不丢失

#### Scenario: 无 url 的来源不渲染链接
- **WHEN** 来源项 `url` 为 `null` 或旧数据无该字段
- **THEN** 来源行按现状纯文本渲染,不出现链接或图标,页面不报错
