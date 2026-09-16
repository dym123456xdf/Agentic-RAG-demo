# 任务清单:在召回阶段使用预处理后的查询

## 1. 重写 `app/rag/retriever.py`

- [ ] 1.1 把 `QueryFusionRetriever` 的构造从 `Retriever.__init__` 里去掉;改为持有一个 `as_retriever = self._index.as_retriever(similarity_top_k=TOP_K)`(直接用 llama-index 的单 retriever)
- [ ] 1.2 新增模块级工具函数 `_reciprocal_rank_fuse(list_of_node_lists, k=60) -> List[NodeWithScore]`:
  - 标准 RRF:`score(d) = sum(1 / (k + rank_in_variant_i(d)))` for each variant
  - 输入每个变体独立 `retrieve()` 得到的 `NodeWithScore` 列表
  - 输出按 RRF score 降序排列的 `NodeWithScore` 列表
  - `node_id` 相同的节点视为同一文档,score 累加
- [ ] 1.3 重写 `Retriever.retrieve(processed: ProcessedQuery)`:
  - 构造变体列表:`[processed.original, processed.rewritten, *processed.expanded]`
  - 用 `dict.fromkeys()` 去重保序(防止 `expanded` 里有 `rewritten` 重复)
  - 对每个变体:`self._index.as_retriever(similarity_top_k=TOP_K).retrieve(v)`
  - 调 `_reciprocal_rank_fuse(...)` 融合
  - 若 `len(fused) < TOP_K`,补一轮 `retrieve(processed.rewritten)` 兜底,然后 `merge_by_node_id`
  - 返回 `fused[:TOP_K]`
- [ ] 1.4 删掉 `_ensure_fuser` / `_fuser` 相关字段(不再需要)
- [ ] 1.5 删掉 `self._llm._llm` 这种戳进 LLMClient 私有字段的耦合 — 现在不需要把 LLM 注入 fuser 了

## 2. Spec 更新

- [ ] 2.1 在 `openspec/changes/use-processed-query-in-retriever/specs/hybrid-retrieval/spec.md` 写 `## ADDED Requirements`:
  - `Requirement: Retrieval consumes preprocessed variants`
  - `Requirement: Reciprocal-rank fusion over preprocessing outputs`
  - `Requirement: Original query always participates in fusion`
- [ ] 2.2 现有 `openspec/specs/hybrid-retrieval/spec.md` 里关于 "QueryFusionRetriever (reciprocal_rerank 模式)" 的 Requirement 在 archive 时改写 — 由 fuser 切换到手动 RRF 是 breaking change 但**对外可观测行为**(top-K 排序、命中分布)不变,只需更新实现侧措辞

## 3. 测试(本仓库无测试,手测清单)

- [ ] 3.1 **单轮无历史**:
  - 上传 `data/sample_kb.md`
  - `POST /chat {"query":"什么是 embedding?","history":[]}`
  - 期望:能正常返回答案,sources 数量 ≥ 1
- [ ] 3.2 **多轮改写**:
  - `POST /chat {"query":"它是怎么工作的?","history":[{"role":"user","content":"什么是 embedding?"},{"role":"assistant","content":"..."}]}`
  - 期望:答案引用了"embedding"相关内容(改前需 fallback 才命中,改后应该直接命中)
- [ ] 3.3 **回归**:同样的查询改前 vs 改后,命中的 chunk 集合**应基本一致**(允许排序小变,但不应掉召回)

## Verification

实施完成后:
- [ ] V.1 `git diff app/rag/retriever.py` 显示:删 `_ensure_fuser` / `_fuser` / LLM 注入;新增 `_reciprocal_rank_fuse` + 重写 `retrieve`
- [ ] V.2 `grep -rn 'QueryFusionRetriever' app/` 应**零结果**(本 change 后这个类不再被使用)
- [ ] V.3 手测 3.1 / 3.2 / 3.3 通过
- [ ] V.4 更新 `CLAUDE.md` §2 "retriever 段"去掉 known-coupling 警告