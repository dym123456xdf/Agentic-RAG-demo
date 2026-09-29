# Spec Delta

## MODIFIED Requirements

### Requirement: 答案来源携带 0-1 置信度

来源列表的每一项 SHALL 携带 `confidence` 字段,为 0-1 区间的浮点(由重排模型原始分归一化得出,原始 `score` 字段保留);流式接口的 `meta` 事件与非流式接口 `POST /chat` 的响应来源列表均携带该字段。

每一项 SHALL 额外携带 `url` 字段(0 或 1 字符串,可为 `null`),为该来源可跳转的原始出处链接:

- `source_type ∈ {web, xhs}`:`url` 为召回时写入的来源 `file_dir`(web 原网页 URL / xhs 笔记链接 `https://www.xiaohongshu.com/explore/<feed_id>`),缺失时 `null`。
- `source_type = vector`(知识库):`url` 按 MinerU 转换产物对象约定拼为相对路径 `/converted/<stem>/<stem>.md`,其中 `stem` = 原文件名(`doc_name`)去后缀;`doc_name` 缺失时 `null`。
- 定位信息缺失(旧数据无 `doc_name` / `file_dir`)一律映射为 `null`,该条不渲染链接。

`url` 随来源落库(JSON 新增该 key),历史回溯接口原样返回;本变更前落库的旧记录无 `url` key,前端按缺省处理。

#### Scenario: 非流式响应带置信度
- **WHEN** 客户端调用 `POST /chat`
- **THEN** 响应 `sources` 每项含 `confidence`(0-1),原有 `score`(原始分)字段不变

#### Scenario: 非流式响应带跳转链接
- **WHEN** 客户端调用 `POST /chat`
- **THEN** 响应 `sources` 每项含 `url`(字符串或 `null`),定位信息缺失时该条 `url` 为 `null`

#### Scenario: 流式 meta 帧带跳转链接
- **WHEN** 流式接口 `POST /chat/stream` 推送 `meta` 事件
- **THEN** 该事件 `sources` 每项与 `POST /chat` 响应同形(含 `url` 字段),历史落库 JSON 同步携带

#### Scenario: 旧历史兼容
- **WHEN** 渲染的历史消息来源数据缺少 `confidence` 或 `url` 字段(旧落库记录)
- **THEN** 界面正常渲染:不显示置信度数值、不显示低置信度提示、来源行保持纯文本不渲染链接,不报错

## ADDED Requirements

### Requirement: 来源行可点击跳转

首页流式渲染与管理页历史回溯共用的来源行 SHALL 在来源项 `url` 非空时,把来源名渲染为可点击跳转链接(新标签页打开,`target="_blank" rel="noopener"`),使读者一键核对原始出处;`url` 为 `null` 或缺失时来源行保持现状纯文本渲染(无链接、无图标、不报错)。跳转链接的视觉表现属 `ui-style` 能力(见其「来源行跳转链接视觉」要求)。

#### Scenario: 有 url 的来源可跳转
- **WHEN** 来源项 `url` 为 `/converted/<stem>/<stem>.md`、web 原 URL 或 xhs 笔记链接
- **THEN** 来源名渲染为带外链图标的链接,点击在新标签页打开该出处,当前会话上下文不丢失

#### Scenario: 无 url 的来源不渲染链接
- **WHEN** 来源项 `url` 为 `null` 或旧数据无该字段
- **THEN** 来源行按现状纯文本渲染,不出现链接或图标,页面不报错
