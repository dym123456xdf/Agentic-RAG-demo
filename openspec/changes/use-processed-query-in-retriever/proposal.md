# 在召回阶段使用预处理后的查询(别再把 `original` 喂给 fuser)

## Why

`app/rag/pre_query.py` 每次请求要打 3 次 LLM:多轮改写 + 意图识别 + 查询扩展。这套预处理的设计意图是"用更准的 query 去检索 → 召回更准 → 答案更好"。

但 `app/rag/retriever.py:retrieve()` 实际是这么调 fuser 的:

```python
self._fuser.retrieve(processed.original)   # ← 把原始问题喂给 fuser
```

预处理产出的 `processed.rewritten`(多轮补全后的 query)和 `processed.expanded`(3 个语义变体)**只**在 `len(nodes) < TOP_K` 时作为 fallback 用一次。

后果:
- 预处理白白烧了 2-3 次 LLM call 的 token(改写 + 扩展),但召回结果**和直接传 `query` 一样**(因为 fuser 内部还会重新做它自己的扩展,根本不知道 `ProcessedQuery` 已经扩展过了)
- 改写 prompt 是为多轮对话设计的(补全指代),不传给 fuser 等于这一段 token 完全浪费
- `processed.expanded` 也是,在展开变体列表上做 fusion 才是它存在的意义,结果只用 `processed.original` 让 fuser 自己重做

## What Changes

让 `Retriever.retrieve()` **真正**用上预处理产物:

### 方案(实施时细化):从 fuser 切到手动 fusion

`QueryFusionRetriever` 内部已经实现了 fusion,但它对传入的 query 字符串会再做一次"生成变体"的步骤,这和我们已经做的扩展**重复**。

替代:**直接用 `processed.expanded` (或 `[original, rewritten, *expanded]` 组合) 作为变体列表,手动对每个变体调 `index.as_retriever().retrieve(v)`,自己做 reciprocal-rank fusion。**

伪代码:
```python
variants = [processed.original, processed.rewritten] + processed.expanded
variants = list(dict.fromkeys(variants))           # 去重保序
results_per_variant = [as_retriever.retrieve(v) for v in variants]
fused = reciprocal_rank_fuse(results_per_variant)  # 自己写,llama-index 有 util
if len(fused) < TOP_K:
    fallback = as_retriever.retrieve(processed.rewritten)
    fused = merge_by_node_id(fused, fallback)
return fused[:TOP_K]
```

**影响范围**:
- 修改:`app/rag/retriever.py`(retriever 主逻辑改写 + 引入 reciprocal-rank fusion 工具)
- 修改:`CLAUDE.md` §2 "代码架构"段(去掉 retriever 的 known-coupling 警告,因为不再"已知问题")
- 修改:`openspec/specs/hybrid-retrieval/spec.md`(archive 时合并)
- 不动:`app/rag/pre_query.py`(它的产物接口刚好够用,不需要改)

**新增能力**(记入 `specs/hybrid-retrieval/spec.md` 的 ADDED Requirements):
- 检索必须使用预处理产物中的 `expanded` 变体做融合,而不是 fuser 内部重新生成
- 多轮对话的 `rewritten` query 必须作为 fusion 的变体之一(而不是仅作 fallback)

## Non-Goals

- **不优化**预处理本身的延迟(3 次 LLM call 是另一个话题)
- **不改** fusion 算法本身(reciprocal_rank 是标准做法,不动 `k=60` 等参数)
- **不引入**额外检索策略(BM25 / hybrid sparse-dense 等都是单独 change)

## Out of Scope

- 改写 prompt 的进一步调优 — 这是 `app/rag/pre_query.py` 的事
- 意图识别结果的下游使用 — 当前意图字段只在 `meta` 里透传给前端,不被检索用,本 change 不动

## Success Criteria

1. 同一个多轮对话 query,改用预处理产物后检索召回的 chunks **数量不变或更多**(语义不变前提下不能掉召回)
2. 单轮无历史的 query(`processed.expanded == [query]`),改后行为**与改前完全一致**(回归)
3. 多轮对话里"它/那个方法/前面提到的"这类指代,**仅靠 `processed.rewritten` 一条变体**就能召回正确文档(改前要靠 fallback 才命中)
4. `processed.original` 直接出现在变体列表里(确保 fuser 内部变体生成被绕过时,原始 query 仍被检索一次)