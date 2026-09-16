"""RAG 流水线 —— 单一职责:按需求文档的 5 段式把模块串成一个 query()。

不持有业务逻辑,只装配 + 转发:
pre_query → retriever → post → generator
"""
from __future__ import annotations

from typing import cast

from app.rag.generator import Generator
from app.rag.indexer import build_from_path
from app.rag.post import PostProcessor
from app.rag.pre_query import QueryPreProcessor
from app.rag.retriever import Retriever


class RAGPipeline:
    """把 5 个 RAG 模块串成一个端到端的 query 接口。"""

    def __init__(self):
        self._pre = QueryPreProcessor()
        self._retriever = Retriever()
        self._post = PostProcessor()
        self._generator = Generator()

    def query(self, question: str, history: list[dict[str, str]] | None = None) -> dict:
        # 1. 预处理
        processed = self._pre.process(question, history)
        # 2. 召回
        raw_nodes = self._retriever.retrieve(processed)
        # 3. 后处理
        top_nodes = self._post.process(raw_nodes, processed.rewritten)
        # 4. 生成
        result: dict = self._generator.generate(processed.rewritten, top_nodes)
        # 5. 附上预处理细节,方便前端调试
        result["meta"] = {
            "intent": processed.intent,
            "rewritten": processed.rewritten,
            "expanded": processed.expanded,
            "raw_count": len(raw_nodes),
            "after_count": len(top_nodes),
        }
        return result

    def ingest(self, path: str) -> dict:
        """入库入口,方便路由直接调。"""
        return cast(dict, build_from_path(path))
