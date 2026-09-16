# rag-pipeline Specification

## Purpose
定义 RAG 五段流水线（查询预处理 → 向量召回 → 后处理 → 答案生成）的行为契约。

## Requirements

### Requirement: 查询预处理
系统 SHALL 将用户原始问题加工为更适合检索的结构化查询，包含意图识别、多轮改写、查询扩展三个子步骤。

#### Scenario: 无历史直接返回
- **WHEN** 用户发送问题且无对话历史
- **THEN** 不触发改写步骤
- **AND** 返回原始问题 + 意图 + 扩展问题

#### Scenario: 有历史补全指代
- **GIVEN** 对话历史中存在上文指代对象
- **WHEN** 用户发送包含"它/这个/那"等指代词的问题
- **THEN** 系统调用 LLM 结合历史补全为独立完整的问题

#### Scenario: 扩展问题去重
- **WHEN** LLM 生成的扩展问题与原问题重复
- **THEN** 去除重复项，最多保留 3 条

### Requirement: 向量召回
系统 SHALL 使用预处理后的查询从 Milvus 召回相关文档片段，支持多路召回融合去重。

#### Scenario: 多路融合召回
- **WHEN** 预处理产出改写问题 + 扩展问题
- **THEN** 对每个变体执行向量召回
- **AND** 使用 RRF 融合去重
- **AND** 返回 TOP_K 条节点

#### Scenario: 召回不足补充
- **GIVEN** 融合召回结果数量低于 TOP_K
- **WHEN** 补充召回仍有新节点
- **THEN** 用改写后问题补一次单路召回并去重

### Requirement: 后处理重排
系统 SHALL 对召回节点执行相似度过滤 + BGE 交叉编码重排，返回 TopN 精修结果。

#### Scenario: 距离阈值过滤
- **WHEN** 节点 Milvus COSINE distance 大于 cutoff
- **THEN** 该节点被过滤

#### Scenario: 重排排序
- **WHEN** 过滤后节点数大于 0
- **THEN** 用 BGE-reranker 重新打分
- **AND** 按分数降序排列，只保留 RERANK_TOP_N 条

### Requirement: 答案生成
系统 SHALL 将重排后节点拼为上下文，调用 LLM 生成答案 + 来源列表。

#### Scenario: 有参考答案
- **WHEN** 重排后节点非空
- **THEN** 拼接上下文调用 LLM
- **AND** 返回 answer + sources（含 index/content/score/source）

#### Scenario: 无参考兜底
- **GIVEN** 重排后节点为空
- **WHEN** 生成阶段执行
- **THEN** 返回固定文案"我不知道,资料里没提到。"且 sources 为空列表

### Requirement: 幂等入库
系统 SHALL 在入库前按文件名查重，已存在的文件跳过不入库。

#### Scenario: 重复文件跳过
- **GIVEN** Milvus 中已有 source="doc.md" 的 chunk
- **WHEN** 再次入库同名文件
- **THEN** 跳过该文件
- **AND** stats.skipped_files 包含 "doc.md"
