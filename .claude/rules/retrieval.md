---
paths:
  - app/core/milvus_hybrid.py
  - app/core/bge_embedding.py
  - app/rag/base.py
  - app/rag/pipeline.py
  - app/rag/query_graph.py
  - app/rag/state.py
  - app/rag/nodes/query_nodes.py
  - app/api/chat.py
  - static/index.html
---

# 检索链路规则

## Milvus 分数两套语义(IMPORTANT,别混)

- 单路 dense COSINE `search()`:返回「距离」,越小越相关
- `milvus_hybrid.hybrid_search()`:score 是 WeightedRanker 融合相似度,越大越相关
- 详见 `app/core/milvus_hybrid.py` 头部注释

## 混合检索与重排

- 混合检索 = dense + sparse 两路,WeightedRanker 融合
- embedding:BGE-M3 本地模型(硬约束:`EMBEDDING_PROVIDER` 只支持 `bge-m3`,换模型必须清空 collection 全量重新入库)
- 重排:BGE-reranker-v2-m3 断崖检测重排;rerank 失败时 fallback 到 rrf_score 排序

## 搜索模式互斥路由(IMPORTANT)

`search_mode ∈ {kb, web, xhs}`,前端下拉三选一,preprocess 后由 conditional_edges 互斥扇出:

| 模式 | 挂载的召回路 |
| --- | --- |
| `kb`(默认,非法值兜底回退) | embedding_search +(`HYDE_ENABLED` 且 intent ∈ {factual, explanatory} 时)hyde_search |
| `web` | 仅 Brave Web 搜索 |
| `xhs` | 仅小红书 MCP 召回(需 `XHS_MCP_ENABLED`,与查询意图无关,用户显式选择优先) |

- 选外部源(web / xhs)时**不查本地库**
- Web / 小红书结果**仅本轮可见、不入库**
- RRF 只在当前模式挂载的路内融合(等权,k = `Config.RRF_K`):kb 至多两路,web / xhs 单路退化为按原顺序
- 闲聊意图不走召回,直接进生成节点

## HyDE

- LLM 生成假设答案,与改写后的 query 拼接,走同一条 `hybrid_search`;只在 kb 模式内按意图规则挂载(向量检索的质量增强,不单独成路)
