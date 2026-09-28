# cliff-rerank Specification

## Purpose

把现有的 BGE 重排(固定 TopK)替换为「BGE 重排 + 断崖检测动态截断」:重排得分为 BGE-reranker-v2-m3 的原始 logit(无界,非 0-1),按降序用「绝对落差」与「相对落差」任一触发即截断,截断后 TopK 收敛到 `[RERANK_MIN_TOPK, RERANK_MAX_TOPK]` 之间;每条结果附 `confidence = sigmoid(score)`(0-1)供前端展示与低置信度提示;阈值由 `.env` 暴露,默认 `RERANK_GAP_ABS=1.0`、`RERANK_GAP_RATIO=0.3`、`RERANK_MIN_TOPK=3`、`RERANK_MAX_TOPK=10`。

## ADDED Requirements

### Requirement: BGE 重排输入

系统 SHALL 由 `cliff_rerank` 节点接 `rrf_chunks` 与查询文本,经本地 `sentence_transformers.CrossEncoder`(`Config.RERANK_MODEL`,默认 BAAI/bge-reranker-v2-m3,设备自动选 mps/cpu)对每个 chunk 打分:`score` 为原始 logit(可正可负、无界),另算 `confidence = sigmoid(score) ∈ [0, 1]`;重排器抛异常时降级使用 RRF 融合分(此时断崖仍生效)。

#### Scenario: 重排打分
- **WHEN** 重排模型对 10 个 chunk 排序
- **THEN** 每条 chunk 携带原始 `score`(logit,无界)与 `confidence`(sigmoid,0-1),按 score 降序进入断崖检测

#### Scenario: 重排模型不可用降级
- **WHEN** CrossEncoder 推理抛异常或超时
- **THEN** 回退使用 `rrf_chunks` 的 RRF 得分作为 `score`,断崖算法照常运行,日志包含 `rerank fallback to rrf`

### Requirement: 断崖检测双阈值算法

系统 SHALL 在 `app/rag/nodes/query_nodes.py` 中实现 `_cliff_cut(sorted_scores, gap_abs, gap_ratio, min_topk, max_topk) -> int`,按 score 降序遍历相邻对 `prev, cur`,在以下任一条件首次成立时截断到当前 rank:

- **绝对落差**:`prev - cur >= gap_abs`
- **相对落差**:`prev > 0 and (prev - cur) / prev >= gap_ratio`

截断 rank SHALL 在 `[min_topk, max_topk]` 内收敛:`cut = max(min_topk, min(cut, max_topk))`;最终返回 `sorted_scores[:cut]`。

#### Scenario: 绝对落差触发
- **WHEN** 排序后相邻 score 序列为 `[0.95, 0.90, 0.40, ...]`,`gap_abs = 1.0` 不触发,但 `0.90 - 0.40 = 0.50` 仍 < 1.0
- **THEN** 改为 `gap_abs = 0.5`,`0.90 - 0.40 = 0.5 >= 0.5` 触发,截断到 rank 3

#### Scenario: 相对落差触发
- **WHEN** 排序后相邻 score 序列为 `[1.0, 0.95, 0.80, 0.60, ...]`,`gap_ratio = 0.3`
- **THEN** `0.95 - 0.80 = 0.15, 0.15 / 0.95 ≈ 0.158 < 0.3` 不触发;但 `0.80 - 0.60 = 0.20, 0.20 / 0.80 = 0.25 < 0.3` 仍不触发(用例说明算法不草率触发)

#### Scenario: 边界收敛
- **WHEN** 原始 `cut = 1`(断崖极早)且 `min_topk = 3`
- **THEN** 实际 cut = `max(3, min(1, 10)) = 3`,保证至少 3 条

#### Scenario: 边界上限
- **WHEN** 原始 `cut = 20`(集合总数很多)且 `max_topk = 10`
- **THEN** 实际 cut = `max(3, min(20, 10)) = 10`,最多 10 条

#### Scenario: 无断崖
- **WHEN** 排序后相邻 score 序列近似均匀(如 `[1.0, 0.97, 0.95, 0.93, ...]`)
- **THEN** 不触发任何断崖,cut = `max_topk`(默认 10)

### Requirement: `.env` 配置可调

系统 SHALL 由 `app/core/config.py` 暴露以下 `.env` 字段,缺省值分别为 `RERANK_GAP_ABS=1.0`、`RERANK_GAP_RATIO=0.3`、`RERANK_MIN_TOPK=3`、`RERANK_MAX_TOPK=10`(重排模型路径由 `RERANK_MODEL` 配置,默认 BAAI/bge-reranker-v2-m3 本地推理,无云端后端开关);任意字段缺失时使用缺省值,不报错。

#### Scenario: 字段读取
- **WHEN** 任意时刻 `Config.RERANK_GAP_ABS` 被读取
- **THEN** 返回 `float`,与 `.env` 同步,缺省为 1.0

#### Scenario: 类型校验
- **WHEN** `.env` 写入 `RERANK_GAP_ABS=abc`
- **THEN** `Config` 初始化时抛 `ValueError` 或 `RuntimeError`,快速失败

### Requirement: 输出与下游契约

`cliff_rerank` 节点 SHALL 把 `reranked_docs` 写入状态,字段含 `{text, doc_name, file_dir, chunk_idx, score, confidence, source_type}`(与 `rrf_chunks` 一致,新增重排 `score` 与 `confidence`);`generate` 节点以 `reranked_docs` 作为 prompt 中的引用材料,不入 Milvus,不入历史。

#### Scenario: 字段齐全
- **WHEN** `reranked_docs` 进入 `generate` 节点
- **THEN** 每条 doc 至少含 `text / doc_name / file_dir / chunk_idx / score / confidence`

#### Scenario: 不入库
- **WHEN** `cliff_rerank` 完成
- **THEN** 不调用 `milvus_hybrid.insert(...)`,Milvus 集合数量不变
