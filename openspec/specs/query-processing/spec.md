# query-processing Specification

## Purpose
定义查询预处理（意图识别 / 多轮改写 / 查询扩展）的行为契约。此能力在 rag-pipeline 中被引用，独立成 spec 便于后续差异化检索策略。

## Requirements

### Requirement: 意图识别
系统 SHALL 将用户问题分类为 factual / explanatory / comparison / creative / chitchat 之一。

#### Scenario: 分类结果在白名单内
- **WHEN** LLM 返回的标签属于白名单
- **THEN** 使用该标签作为 intent

#### Scenario: 分类结果不在白名单
- **GIVEN** LLM 返回 "unknown" 或空字符串
- **WHEN** 预处理器收到结果
- **THEN** fallback 到 "factual"

### Requirement: 多轮改写
系统 SHALL 在有对话历史时，结合历史补全指代词和省略主语。

#### Scenario: 无历史跳过
- **WHEN** history 为空
- **THEN** 不调用改写，直接返回原问题

#### Scenario: 有历史改写
- **GIVEN** history 包含最近 3 轮对话
- **WHEN** 用户问"它多少钱？"
- **THEN** 改写为包含商品名的独立问题

### Requirement: 查询扩展
系统 SHALL 生成最多 3 个语义相关的扩展问题，用于扩大召回覆盖面。

#### Scenario: 正常扩展
- **WHEN** 用户提问非闲聊类问题
- **THEN** 返回 1-3 条扩展问题
- **AND** 去除与原问题重复的项
