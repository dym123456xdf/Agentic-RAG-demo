"""后处理器 —— 单一职责:把召回的 TopK 节点精修成 TopN。

两步:
1. 相似度阈值过滤(SimilarityPostprocessor),砍掉明显不相关的
2. BGE-reranker-v2-m3 重新打分排序,只留最相关的 N 条

BGE 模型加载较慢(~13s 冷启),用模块级 lazy 单例,只在第一次调用时实例化。
"""
from __future__ import annotations

from typing import List

from llama_index.core.schema import NodeWithScore
from sentence_transformers import CrossEncoder

from app.core.config import Config


_BGE = None


def _get_reranker() -> CrossEncoder:
    global _BGE
    if _BGE is None:
        # Apple Silicon 走 MPS,没 GPU 自动 fallback 到 CPU
        import torch
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        _BGE = CrossEncoder(Config.RERANK_MODEL, device=device)
    return _BGE


class PostProcessor:
    def __init__(self):
        # 不再用 llama-index 的 SimilarityPostprocessor:
        # 它假设 score 是 similarity(越大越相关),但 Milvus COSINE distance 是越小越相关,
        # 语义反了,设阈值会误伤。下面直接交给 BGE 重排做精修,语义更准。
        self._top_n = Config.RERANK_TOP_N
        self._cutoff = Config.SIMILARITY_CUTOFF  # 留口子:distance 大于 cutoff 直接砍

    def process(self, nodes: List[NodeWithScore], query: str) -> List[NodeWithScore]:
        if not nodes:
            return nodes

        # 1. distance 阈值过滤(distance 越大越不相关)
        filtered = [n for n in nodes if n.score is not None and n.score <= self._cutoff]
        if not filtered:
            return filtered

        # 2. BGE 重排
        reranker = _get_reranker()
        pairs = [(query, n.node.get_content()) for n in filtered]
        scores = reranker.predict(pairs, show_progress_bar=False)
        for n, s in zip(filtered, scores):
            n.score = float(s)

        filtered.sort(key=lambda x: x.score, reverse=True)
        return filtered[: self._top_n]