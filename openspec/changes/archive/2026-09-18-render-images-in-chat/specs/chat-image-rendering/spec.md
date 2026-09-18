# Spec Delta

## Purpose

让用户在问答链路的每一处(首页实时回答、首页会话回溯、管理页历史回溯)都能直接看到答案引用的知识库文档配图,而不是 markdown 图片语法原文;并约束答案生成不得改写或编造图片路径,保证引用可被前端安全渲染。

## ADDED Requirements

### Requirement: 聊天回答渲染知识库图片

首页实时回答中,答案内形如 `![alt](/converted/...)` 的图片引用 SHALL 被渲染为可显示的图片元素,而非 markdown 原文;图片必须能通过服务端 `/converted` 静态路由真实加载。

#### Scenario: 实时回答显示图片
- **WHEN** 用户对含图文档提问,答案中包含 `![image](/converted/<name>/images/<hash>.jpeg)`
- **THEN** 首页聊天气泡内该处显示图片本体,不显示 `![...](...)` 语法原文

#### Scenario: 首页会话回溯同样渲染
- **WHEN** 用户切换到历史会话,回溯的答案消息中包含 `/converted/` 前缀的图片引用
- **THEN** 回溯消息与实时回答以相同方式渲染图片

### Requirement: 历史回溯渲染一致

管理页问答历史中展示的答案 SHALL 与首页采用同一图片渲染规则:答案内的 `/converted/` 图片引用渲染为图片,其余内容(来源、meta 折叠等)展示行为不变。

#### Scenario: 管理页历史显示图片
- **WHEN** 用户在管理页历史回溯中查看包含 `/converted/` 图片引用的历史答案
- **THEN** 该答案渲染出图片,来源与 meta 的折叠展开行为不受影响

### Requirement: 仅放行 `/converted/` 前缀的图片

被渲染为图片元素的引用 src SHALL 仅限以 `/converted/` 开头的 URL;其余任何图片语法(相对路径、任意绝对路径、外部 URL)SHALL 按原文文本显示,且不得触发网络加载。渲染过程中图片语法之外的文本 SHALL 保持 HTML 转义。

#### Scenario: 非 `/converted/` 引用按原文显示
- **WHEN** 答案中包含 `![x](images/foo.jpeg)` 或 `![x](http://example.com/a.jpg)`
- **THEN** 该引用按原文文本显示,浏览器不发起对应图片请求

#### Scenario: alt 与文本中的特殊字符不破坏页面
- **WHEN** 图片 alt 或答案文本中包含 `<script>`、引号等 HTML 特殊字符
- **THEN** 全部按文本显示,不产生可执行的 HTML 注入

### Requirement: 答案生成保真图片引用

答案生成 SHALL 原样保留参考资料中出现的信息,其中图片引用必须逐字保留(路径不得改写、缩写或编造);参考资料不含图片引用时,答案不得新增任何图片引用。

#### Scenario: 资料含图则答案原样引用
- **WHEN** 检索参考资料中含 `![image](/converted/<name>/images/<hash>.jpeg)` 且答案需要引用该图
- **THEN** 答案中的图片引用与资料逐字一致

#### Scenario: 资料无图则不编造
- **WHEN** 检索参考资料中不含任何图片引用
- **THEN** 答案中不出现任何图片语法,不出现磁盘上不存在的图片路径
