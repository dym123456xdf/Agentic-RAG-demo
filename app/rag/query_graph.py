"""查询 StateGraph 装配 —— preprocess → 按搜索模式互斥路由到单类召回 → RRF → 断崖重排 →(生成)。

编译两个产物:
- RETRIEVAL_GRAPH:preprocess → 按 search_mode 互斥路由挂载 1~2 路召回(kb → 向量 + HyDE;
  web / xhs → 单路外部)→ rrf_fuse → cliff_rerank → END。流式出口用:跑完拿到完整终态
  (intent / search_mode / rewritten_query / 各路 chunks / reranked_docs),由 pipeline.query_stream
  在图外用 LLMClient.stream_chat 逐 token 产出 —— llama-index 的 LLM 不发 LangChain 事件,
  astream_events 拿不到 token 增量,不能依赖它做流式。
- QUERY_GRAPH:RETRIEVAL_GRAPH 之后接 generate 节点,非流式整图一次跑完。

并发模型(搜索模式互斥路由):
- preprocess 之后,add_conditional_edges 把控制权交给 route_after_preprocess,
  返回的节点名列表让 LangGraph 按 add_edge 关系调度对应节点。互斥路由下任一时刻
  至多两路(kb:向量 + HyDE 并行),web / xhs 单路,chitchat 直达 cliff_rerank。
- 挂载的各路召回均汇向 rrf_fuse,LangGraph 会等待所有上游结束才触发 rrf_fuse(汇合语义)。
- 各节点增量返回(只写自己的 key),避免同一 superstep 并发写公共 key 崩溃。
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.rag.nodes import (
    NodeCliffRerank,
    NodeEmbeddingSearch,
    NodeGenerate,
    NodeHydeSearch,
    NodePreprocess,
    NodeRrfFuse,
    NodeWebSearch,
    NodeXhsSearch,
)
from app.rag.nodes.query_nodes import route_after_preprocess
from app.rag.state import QueryGraphState


def _build(with_generate: bool):
    """装配查询图;with_generate 决定是否挂 generate 节点(流式走检索子图)。"""
    builder = StateGraph(QueryGraphState)
    builder.add_node("preprocess", NodePreprocess())
    builder.add_node("embedding_search", NodeEmbeddingSearch())
    builder.add_node("hyde_search", NodeHydeSearch())
    builder.add_node("web_search", NodeWebSearch())
    builder.add_node("xhs_search", NodeXhsSearch())
    builder.add_node("rrf_fuse", NodeRrfFuse())
    builder.add_node("cliff_rerank", NodeCliffRerank())

    builder.set_entry_point("preprocess")

    # preprocess 之后按搜索模式互斥路由到 1~2 路召回;chitchat(闲聊)直达 cliff_rerank 跳过检索
    builder.add_conditional_edges(
        "preprocess",
        route_after_preprocess,
        {
            "embedding_search": "embedding_search",
            "hyde_search": "hyde_search",
            "web_search": "web_search",
            "xhs_search": "xhs_search",
            "cliff_rerank": "cliff_rerank",
        },
    )

    # 挂载的各路均汇向 rrf_fuse(未挂载的路不会被调度,不影响汇合)
    builder.add_edge("embedding_search", "rrf_fuse")
    builder.add_edge("hyde_search", "rrf_fuse")
    builder.add_edge("web_search", "rrf_fuse")
    builder.add_edge("xhs_search", "rrf_fuse")
    builder.add_edge("rrf_fuse", "cliff_rerank")

    if with_generate:
        builder.add_node("generate", NodeGenerate())
        builder.add_edge("cliff_rerank", "generate")
        builder.add_edge("generate", END)
    else:
        builder.add_edge("cliff_rerank", END)

    return builder.compile()


# 检索子图(流式出口用):终态含 meta 需要的全部字段
RETRIEVAL_GRAPH = _build(with_generate=False)
# 完整图(非流式):检索 + 生成一次跑完
QUERY_GRAPH = _build(with_generate=True)
