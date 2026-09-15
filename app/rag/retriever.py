"""检索器 —— 单一职责:用预处理过的 query 召回到 TopK 节点。

策略:
- 默认走 QueryFusionRetriever:对扩展后的多个 query 各自向量召回,融合去重,覆盖面更广。
- 融合需要 LLM 生成"最终 query" —— 这里直接用改写后的 query 跑一次向量召回做兜底。
"""
from __future__ import annotations

from typing import List

from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.schema import NodeWithScore

from app.core.config import Config
from app.core.llm import LLMClient
from app.rag.indexer import load_existing_index
from app.rag.pre_query import ProcessedQuery


class Retriever:
    def __init__(self):
        self._index = load_existing_index()
        # QueryFusionRetriever 要 LLM 帮它"生成 query 变体";不传就 fallback 到 OpenAI 默认
        # 这里显式注入我们的 M3,封装跟 Settings 解耦
        self._llm = LLMClient()
        self._fuser: QueryFusionRetriever | None = None

    def _ensure_fuser(self, num_queries: int):
        if self._fuser is None or self._fuser.num_queries != num_queries:
            base = self._index.as_retriever(similarity_top_k=Config.TOP_K)
            self._fuser = QueryFusionRetriever(
                [base],
                llm=self._llm._llm,        # 显式注入,避免 fallback OpenAI
                similarity_top_k=Config.TOP_K,
                num_queries=num_queries,
                mode="reciprocal_rerank",
                use_async=False,
            )

    def retrieve(self, processed: ProcessedQuery) -> List[NodeWithScore]:
        # 拿改写后的 query + 扩展 query,共 num 条
        queries = [processed.rewritten] + processed.expanded
        self._ensure_fuser(num_queries=len(queries))
        nodes = self._fuser.retrieve(processed.original)  # fuser 内部会自己再扩,我们传 original 即可
        # 如果 fuser 没召回够(扩展不足),用 rewritten 再补一次单条召回
        if len(nodes) < Config.TOP_K:
            base = self._index.as_retriever(similarity_top_k=Config.TOP_K)
            extra = base.retrieve(processed.rewritten)
            seen = {n.node.node_id for n in nodes}
            for n in extra:
                if n.node.node_id not in seen:
                    nodes.append(n)
                    seen.add(n.node.node_id)
        return nodes[: Config.TOP_K]