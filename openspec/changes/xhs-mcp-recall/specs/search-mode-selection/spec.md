# Spec Delta

## Purpose

让用户在首页按次选择搜索模式(仅知识库 / 联网搜索 / 小红书),模式互斥地决定查询图挂载哪一路召回 —— 选外部检索时不查本地知识库,选知识库时不发起外部调用;首页提供下拉选择器,选项按部署可用性过滤并记住上次选择。

## ADDED Requirements

### Requirement: 问答请求携带搜索模式

`POST /chat` 与 `POST /chat/stream` 的请求体 SHALL 增加可选字段 `search_mode`,取值限定 `kb`(仅知识库,默认)/ `web`(联网搜索)/ `xhs`(小红书);缺省或省略时按 `kb` 处理(行为与引入该字段前一致);取值不在允许集合内,或取值对应的外部源主开关未启用(`web` 需 `WEB_SEARCH_ENABLED`、`xhs` 需 `XHS_MCP_ENABLED`)时 SHALL 返回 4xx 拒收。该模式对两出口 SHALL 语义一致。

#### Scenario: 缺省为仅知识库
- **WHEN** 请求未携带 `search_mode`
- **THEN** 按默认值 `kb` 处理,走向量 + HyDE 召回,与旧版行为一致

#### Scenario: 选择联网
- **WHEN** 请求携带 `search_mode: "web"` 且 `WEB_SEARCH_ENABLED == True`
- **THEN** 仅 `web_search` 一路挂载,`embedding_search` / `hyde_search` 不执行,答案仅基于联网结果

#### Scenario: 选择未启用的模式
- **WHEN** 请求携带 `search_mode: "xhs"` 但 `XHS_MCP_ENABLED == False`
- **THEN** 返回 4xx 拒收,不进入检索流程

#### Scenario: 非法取值
- **WHEN** 请求携带 `search_mode: "baidu"`
- **THEN** 返回 4xx 拒收,不进入检索流程

### Requirement: 可用模式配置端点

系统 SHALL 提供 `GET /api/config` 端点,返回 `{"web_search_enabled": bool, "xhs_enabled": bool}`,反映部署级主开关(`WEB_SEARCH_ENABLED` / `XHS_MCP_ENABLED`)状态;前端据此决定下拉中渲染哪些模式选项。

#### Scenario: 反映主开关
- **WHEN** `WEB_SEARCH_ENABLED=true`、`XHS_MCP_ENABLED=false`
- **THEN** 端点返回 `web_search_enabled=true, xhs_enabled=false`

### Requirement: 首页搜索模式下拉选择器

首页输入区 SHALL 提供下拉列表:「仅知识库」恒有;「联网搜索」「小红书」按 `GET /api/config` 的可用性渲染(源不可用时隐藏对应选项);两个外部源均不可用时下拉 SHALL 整体隐藏(页面与无此控件时一致)。用户选择 SHALL 随每次提问以 `search_mode` 字段发送;选择 SHALL 存入 localStorage,下次进入页面恢复上次选择(恢复值已不可用时回落「仅知识库」),默认「仅知识库」。选择仅决定召回路由,不影响闲聊分支。

#### Scenario: 选项按可用性过滤
- **WHEN** 页面加载时 `xhs_enabled=false`
- **THEN** 下拉只含「仅知识库」与「联网搜索」

#### Scenario: 全部外部源不可用
- **WHEN** 页面加载时 `web_search_enabled=false` 且 `xhs_enabled=false`
- **THEN** 下拉控件整体隐藏,页面与引入前一致

#### Scenario: 选择随请求发送
- **WHEN** 用户选择「小红书」并提交问题
- **THEN** 请求体 `search_mode == "xhs"`,仅小红书路挂载

#### Scenario: 记住上次选择
- **WHEN** 用户选择「联网搜索」后刷新页面且该模式仍可用
- **THEN** 下拉恢复为「联网搜索」

#### Scenario: 闲聊不受选择影响
- **WHEN** 用户选择「联网搜索」但意图识别为 `chitchat`
- **THEN** 全部召回路(含外部)仍被跳过,直接闲聊回应

### Requirement: 模式互斥路由

查询图 SHALL 按搜索模式互斥地挂载召回路,任一时刻至多一路外部检索与本地召回不同时存在:`kb` 模式挂载 `embedding_search`(及按现行意图规则的 `hyde_search`);`web` 模式仅挂载 `web_search`;`xhs` 模式仅挂载 `xhs_search`。`chitchat` 意图在任何模式下 SHALL 跳过全部召回。挂载路由 SHALL 不依赖意图分类结果选择外部路(用户显式选择优先);HyDE 仍按意图规则(`intent in {factual, explanatory}` 且 `HYDE_ENABLED`)在 `kb` 模式内决定是否挂载。

#### Scenario: web 模式不查库
- **WHEN** `search_mode == "web"`,意图为 `factual`
- **THEN** 仅 `web_search` 执行,`embedding_search` / `hyde_search` 均不入图,`recall_paths` 仅含 `web`

#### Scenario: xhs 模式任何非闲聊意图均挂载
- **WHEN** `search_mode == "xhs"`,意图为 `explanatory` 或 `comparison`
- **THEN** `xhs_search` 挂载(不因非 factual 意图被拦截),`recall_paths` 仅含 `xhs`

#### Scenario: kb 模式维持现行规则
- **WHEN** `search_mode == "kb"`,意图为 `factual` 且 `HYDE_ENABLED == True`
- **THEN** `embedding_search` 与 `hyde_search` 挂载,行为与引入模式选择前一致
