"""RAG 流水线 —— 单一职责:按需求文档的 5 段式把模块串成 query() / query_stream()。

不持有业务逻辑,只装配 + 转发:
pre_query → retriever → post → generator

query_stream 产出事件元组 (事件名, 载荷),供 /chat/stream 路由包 SSE 帧:
meta -> delta* -> done;检索或生成异常 -> error(与 done 二选一)。
"""
from __future__ import annotations

from typing import Iterator, cast

from app.core.config import Config
from app.rag.generator import Generator, build_sources
from app.rag.indexer import build_from_path
from app.rag.post import PostProcessor
from app.rag.pre_query import QueryPreProcessor
from app.rag.retriever import Retriever


class RAGPipeline:
    """把 5 个 RAG 模块串成端到端 query 接口(非流式 + 流式两个出口)。"""

    def __init__(self):
        self._pre = QueryPreProcessor()
        self._retriever = Retriever()
        self._post = PostProcessor()
        self._generator = Generator()

    def _retrieve(self, question: str, history: list[dict[str, str]] | None):
        """前 3 段(预处理 + 召回 + 重排),两个 query 出口共用。"""
        processed = self._pre.process(question, history)
        raw_nodes = self._retriever.retrieve(processed)
        top_nodes = self._post.process(raw_nodes, processed.rewritten)
        meta = {
            "intent": processed.intent,
            "rewritten": processed.rewritten,
            "expanded": processed.expanded,
            "raw_count": len(raw_nodes),
            "after_count": len(top_nodes),
        }
        return processed, raw_nodes, top_nodes, meta

    def query(self, question: str, history: list[dict[str, str]] | None = None) -> dict:
        processed, raw_nodes, top_nodes, meta = self._retrieve(question, history)
        # 4. 生成
        result: dict = self._generator.generate(processed.rewritten, top_nodes)
        # 5. 附上预处理细节,方便前端调试
        result["meta"] = meta
        return result

    def query_stream(self, question: str,
                     history: list[dict[str, str]] | None = None) -> Iterator[tuple[str, object]]:
        """流式 query:逐事件 yield,事件顺序 meta -> delta* -> done | error。

        - meta 载荷: {sources, confidence(top1), low_confidence, threshold, meta}
          —— 检索+重排一完成就 yield,前端此刻即可渲染参考来源块(感知提速的大头)。
        - done 载荷:完整答案全文(路由据此落库);error 载荷:错误说明,之后直接 return。
        """
        try:
            processed, raw_nodes, top_nodes, meta = self._retrieve(question, history)
        except Exception as e:
            yield "error", f"检索失败: {e}"
            return

        # 主证据 = 重排后 top1;sources 已按相关度降序
        confidence = getattr(top_nodes[0], "confidence", None) if top_nodes else None
        low_confidence = confidence is not None and confidence < Config.CONFIDENCE_THRESHOLD
        yield "meta", {
            "sources": build_sources(top_nodes),
            "confidence": confidence,
            "low_confidence": low_confidence,
            "threshold": Config.CONFIDENCE_THRESHOLD,
            "meta": meta,
        }

        stream, _ = self._generator.generate_stream(processed.rewritten, top_nodes)
        parts: list[str] = []
        try:
            for chunk in stream:
                parts.append(chunk)
                yield "delta", chunk
        except Exception as e:
            # 生成阶段不可恢复错误:推 error 收场,半成品答案不进 done(路由据此不落库)
            yield "error", f"答案生成失败: {e}"
            return
        yield "done", "".join(parts)

    def ingest(self, path: str) -> dict:
        """入库入口,方便路由直接调。"""
        return cast(dict, build_from_path(path))
