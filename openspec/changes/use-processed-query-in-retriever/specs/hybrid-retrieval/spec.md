# 混合检索 — 未来状态(使用预处理后的查询)

> 本文件描述 `use-processed-query-in-retriever` 这个 change 的**未来状态**。
> 它会在本 change 归档时合并进 `openspec/specs/hybrid-retrieval/spec.md`。
> 在那之前,`openspec/specs/hybrid-retrieval/spec.md` 描述的是当前已部署版本(使用 QueryFusionRetriever + `processed.original`)。

## ADDED Requirements

### Requirement: Retrieval consumes preprocessed variants

召回阶段 **SHALL** 使用查询预处理产出的变体列表作为 fusion 阶段的输入,**SHALL NOT** 自己再生成变体。

#### Scenario: 预处理产出了扩展变体

- **WHEN** 预处理器在 `expanded` 里返回了一条或多条变体
- **THEN** retriever **SHALL** 对每个变体各发一次检索
- **AND** retriever **SHALL NOT** 再发任何由召回阶段自己生成 query 的检索

#### Scenario: 多轮改写参与了

- **WHEN** 预处理器改写了 query(因为存在 history)
- **THEN** 改写后的 query **SHALL** 进入 fusion 的变体列表
- **AND** 原始 query **SHALL** 也一并进入

### Requirement: Reciprocal-rank fusion over preprocessing outputs

retriever **SHALL** 用 reciprocal-rank fusion(`k=60`)对每个变体的结果列表做融合。

#### Scenario: Fusion 输出

- **WHEN** 多个变体各自返回了一条或多条 chunk
- **THEN** 每个唯一 chunk **SHALL** 拿到一个融合分数,等于它在各变体里 `1 / (k + rank)` 的累加
- **AND** 结果列表 **SHALL** 按融合分数降序排列
- **AND** 并列时 **SHALL** 按该 chunk 最早出现的 rank 决胜

### Requirement: Original query always participates in fusion

retriever **SHALL** 始终把用户的原始字面 query 纳入变体列表,无论预处理产出了什么。

#### Scenario: 保留原始 query

- **WHEN** `processed.original` 与 `processed.rewritten` 不同(多轮场景)
- **THEN** 两者 **SHALL** 作为两条独立变体出现在 fusion 输入中
- **AND** 去重步骤 **SHALL NOT** 把它们合并成一条

#### Scenario: 无历史时合并

- **WHEN** 没有 history,且 `processed.rewritten == processed.original`
- **THEN** 变体列表 **SHALL** 把它们去重成一条
- **AND** 这唯一一条 **SHALL** 仍然参与检索