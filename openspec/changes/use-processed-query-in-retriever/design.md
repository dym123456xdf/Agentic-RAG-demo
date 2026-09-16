# 设计:在召回阶段使用预处理后的查询

## Context

`QueryFusionRetriever` 是 llama-index 的便利类:`fuser.retrieve(q)` → 内部用 LLM 生成 N 个 query 变体 → 对每个变体调底层 retriever → 融合。

这个便利类对本仓库有个**根本问题**:它对输入 `q` 字符串再生成变体,**完全无视**我们已经用 `QueryPreProcessor` 生成好的 `ProcessedQuery.expanded`。结果:
- 预处理烧 token 烧在 `expanded` 上
- fuser 收到 `processed.original`,自己又重新生成一组变体
- 两边独立工作,预处理产物白做

这是个**集成 bug** — 两个本应协作的组件被错位连接。

## Decisions

### 拆掉 fuser,自己实现 fusion

`QueryFusionRetriever` 对本仓库价值不大,因为:
1. 变体生成部分由 `QueryPreProcessor` 接管了
2. RRF(reciprocal rank fusion)是教科书算法,十几行能写完
3. 拆掉后,`retriever.py` 不再需要 `self._llm._llm` 这种戳私有字段的耦合

### 变体列表构造

```python
variants = [processed.original, processed.rewritten, *processed.expanded]
variants = list(dict.fromkeys(variants))   # 去重保序
```

为什么这样排:
- `original` 一定参与:语义直白时 fuser 变体生成也救不了它
- `rewritten` 一定参与:多轮对话的核心收益
- `expanded` 排在最后:补充语义变体,有就有,没有也不影响

### RRF 参数 `k=60`

标准默认值,出自 Cormack et al. 2009 的原论文。本仓库数据规模小,k 取 60 / 30 / 10 差异不大,不调整。

### Fallback 逻辑保留

`len(fused) < TOP_K` 时仍然补一轮 `retrieve(processed.rewritten)`,这与现状一致 — 唯一变化是 fallback 不再是"变体没生效的补救",而是"融合结果不够多"的兜底。

## Alternatives Considered

### 方案 1:让 fuser 接收 `expanded` 列表

llama-index 的 `QueryFusionRetriever` 接受 `query_gen_prompt` 自定义,但**不接受**外部传入的 query 列表。要绕过这个限制需要 subclass 重写,比手动实现 RRF 更绕。

**放弃原因**:代码量更大、可读性更差、还留下对 fuser 的耦合。

### 方案 2:不做 fusion,只把 `rewritten` 喂给单 retriever

最简单,但放弃了 `expanded` 的语义覆盖价值。

**放弃原因**:至少要做 baseline 看效果再说,直接砍掉 fusion 不是工程判断是赌博。

### 方案 3:在 `pre_query.py` 里去掉 `_expand` 调用

承认 expanded 没用,让 fuser 内部生成。

**放弃原因**:`_expand` 不只为检索服务 — 它还是 `meta` 字段的一部分(供前端调试和未来的"展示候选问题"用)。删掉会破坏契约。

## Verification Hook

archive 前验证:
1. 单轮查询:**行为不变**(fuser 内部生成的变体集合和我们手动构造的变体集合,在 `processed.expanded == [query]` 时近似等价)
2. 多轮查询:指代补全生效(`rewritten` 直接命中正确文档,不再需要 fallback)
3. 召回不掉:同样的 query,改前 vs 改后命中的 chunks 集合基本一致

## Explicit Non-Designs

- **不优化** fusion 算法(不引入 Cross-Encoder 重新打分 — 那是 `app/rag/post.py` 的事)
- **不引入** query-level caching(同样的 query 复用检索结果 — 单独 change)
- **不改** `ProcessedQuery` 数据结构(接口够用)