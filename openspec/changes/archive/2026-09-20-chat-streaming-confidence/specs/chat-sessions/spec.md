# Spec Delta

## MODIFIED Requirements

### Requirement: 聊天请求绑定会话

问答接口 `POST /chat` 的请求体 SHALL 为 `{question, session_id}`:`question` 为必填非空问题文本,`session_id` 为已存在会话的标识。响应保持现有结构(答案 + 来源列表 + meta);来源列表每项在既有字段(`index`/`content`/`score`/`source`)基础上新增 `confidence`(0-1 浮点,重排分归一化)。历史消息落库的来源数据随之携带 `confidence`,旧记录缺失该字段时读取与渲染必须正常兼容。

#### Scenario: 在指定会话中提问

- **WHEN** 客户端携带已存在的 `session_id` 与非空 `question` 调用 `/chat`
- **THEN** 系统返回答案、来源列表(每项含 `confidence`)与 meta,并将该问答对(问题、答案、来源、meta)完整落库

#### Scenario: 会话不存在

- **WHEN** 客户端携带不存在的 `session_id` 调用 `/chat`
- **THEN** 系统返回 404 错误,信息指明会话不存在,不产生任何落库记录

#### Scenario: 问题为空

- **WHEN** `question` 为空或缺失
- **THEN** 系统返回 400 错误,不调用 LLM、不落库
