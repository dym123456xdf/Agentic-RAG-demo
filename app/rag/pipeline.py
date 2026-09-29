"""RAG 流水线 —— 单一职责:对外暴露 LangGraph 薄壳,把图包装成 3 个入口函数。

- ingest(task_id, file_path)         入库入口
- query(question, history, session_id, message_id)            非流式查询
- query_stream(question, history, session_id, message_id)    流式查询(逐事件 yield)

入口仅做参数封装 + 图驱动,不持有业务逻辑;业务逻辑全在各节点。
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
from pathlib import Path
from typing import AsyncIterator, Iterator

from app.core.config import Config
from app.rag.ingest_graph import INGEST_GRAPH
from app.rag.query_graph import QUERY_GRAPH, RETRIEVAL_GRAPH
from app.rag.state import create_default_import_state, create_default_query_state


# ============== 入库 ==============

async def ingest(task_id: str, file_path: str) -> dict:
    """异步入库入口:file_path 为 MinIO 对象 key(如 "uploads/报告.pdf")。"""
    state = create_default_import_state(task_id=task_id, import_file_path=file_path)
    result = await INGEST_GRAPH.ainvoke(state)
    return {
        "task_id": result.get("task_id", task_id),
        "file_title": result.get("file_title", ""),
        "chunks_ingested": result.get("chunks_ingested", 0),
        "uploaded_objects": result.get("uploaded_objects", 0),
    }


# ============== 非流式查询 ==============

async def query(question: str, history: list[dict] | None,
                session_id: int | str = 0, message_id: int | str = 0,
                search_mode: str = "kb") -> dict:
    """非流式:跑完整个图后返回 {answer, sources, meta}。

    异步签名:必须被 await,否则会拿到一个未启动的 coroutine 对象。
    query_stream() 与 RAGPipeline.query_stream() 仍是同步,因为 SSE 的 event_stream()
    由 FastAPI 跑在线程池里(无事件循环),可用 asyncio.run 桥接。
    search_mode(kb / web / xhs)决定查询图互斥挂载哪一路召回,缺省 kb(行为与旧版一致)。
    """
    state = create_default_query_state(
        session_id=session_id,
        message_id=message_id,
        original_query=question,
        history=history or [],
        is_stream=False,
        search_mode=search_mode,
    )
    final = await QUERY_GRAPH.ainvoke(state)
    return _build_response(final)


def _build_response(final: dict) -> dict:
    """从 graph 终态提取 {answer, sources, meta},与旧 pipeline.py 同形。"""
    docs = final.get("reranked_docs") or []
    sources = _build_sources(docs)
    confidence = sources[0]["confidence"] if sources else None
    low_confidence = confidence is not None and confidence < Config.CONFIDENCE_THRESHOLD
    return {
        "answer": final.get("answer", ""),
        "sources": sources,
        "meta": {
            "intent": final.get("intent", ""),
            "rewritten": final.get("rewritten_query", ""),
            "search_mode": final.get("search_mode", "kb"),
            "raw_count": _raw_count(final),
            "after_count": len(docs),
            "recall_paths": _recall_paths(final),
            "confidence": confidence,
            "low_confidence": low_confidence,
            "threshold": Config.CONFIDENCE_THRESHOLD,
        },
    }


def _build_sources(docs: list[dict]) -> list[dict]:
    return [
        {
            "index": i,
            "content": (d.get("text") or "").strip()[:300],
            "score": round(float(d.get("score", 0.0)), 4),
            "confidence": d.get("confidence"),
            "source": d.get("doc_name") or "unknown",
            "source_type": d.get("source_type", "vector"),
            "url": _source_url(d),
        }
        for i, d in enumerate(docs, 1)
    ]


def _source_url(d: dict) -> str | None:
    """把重排文档映射为可跳转的原始出处链接;定位信息缺失返回 None(该条不渲染链接)。

    映射规则(chat-source-links D1/D2 + xhs-source-links D1/D2/D3):
    - web: 召回时已把原 URL 写进 file_dir,直接透出;
    - xhs: file_dir 是裸笔记链接,小红书强制校验 xsec_token,裸链打开只见
      「笔记暂时无法浏览」/登录墙 —— 需追加 ?xsec_token=<token>&xsec_source=pc_feed
      (格式与上游 xiaohongshu-mcp makeFeedDetailURL 逐字一致),token 取召回时
      存入 metadata 的 xsec_token;缺 token 退回裸链(不劣化为 null);
    - vector(知识库): 按 MinerU 转换产物对象约定拼 /converted/<stem>/<stem>.md
      (经既有 /converted 代理路由回放 MinIO),stem = 原文件名去后缀。
      不做逐条 MinIO 存在性探测:未转换的文件得到 404 属可接受弱链接。
    """
    st = d.get("source_type", "vector")
    file_dir = (d.get("file_dir") or "").strip()
    doc_name = (d.get("doc_name") or "").strip()
    if st == "web":
        return file_dir or None
    if st == "xhs":
        if not file_dir:
            return None
        token = ((d.get("metadata") or {}).get("xsec_token") or "").strip()
        return f"{file_dir}?xsec_token={token}&xsec_source=pc_feed" if token else file_dir
    stem = Path(doc_name).stem if doc_name else ""
    return f"/converted/{stem}/{stem}.md" if stem else None


def _recall_paths(final: dict) -> list[str]:
    """按当前搜索模式输出实际挂载的召回路(kb → dense/hyde,web → web,xhs → xhs)。"""
    mode = final.get("search_mode", "kb")
    paths: list[str] = []
    if mode == "web":
        if final.get("web_search_docs"):
            paths.append("web")
    elif mode == "xhs":
        if final.get("xhs_search_docs"):
            paths.append("xhs")
    else:  # kb(默认 / 未知值兜底):向量 + HyDE
        if final.get("embedding_chunks"):
            paths.append("dense")
        if final.get("hyde_embedding_chunks"):
            paths.append("hyde")
    return paths


# 各模式对应的「原始召回」状态字段(非挂载路不计入)
_RAW_FIELDS_BY_MODE = {
    "web": ("web_search_docs",),
    "xhs": ("xhs_search_docs",),
}


def _raw_count(final: dict) -> int:
    """当前模式下实际召回路的原始条数之和(web / xhs 单路;kb 为向量 + HyDE)。"""
    mode = final.get("search_mode", "kb")
    fields = _RAW_FIELDS_BY_MODE.get(
        mode, ("embedding_chunks", "hyde_embedding_chunks")
    )
    return sum(len(final.get(f) or []) for f in fields)


# ============== 流式查询 ==============

# 节点(图内 key)完成 → 推给前端的阶段文案。agnes 等模型下检索前有多次 LLM 串行调用,
# 首字前 40s+ 只见"检索中…"会被当成卡死(2026-09-28 实测),按节点推进给阶段反馈
_STAGE_MSGS = {
    "preprocess": "理解完成,多路召回中(向量 + HyDE)…",
    "embedding_search": "向量召回完成…",
    "hyde_search": "HyDE 召回完成…",
    "web_search": "Web 检索完成…",
    "xhs_search": "小红书检索完成…",
    "rrf_fuse": "多路融合完成,重排打分中…",
}

# 按搜索模式区分「召回中」阶段文案(外部模式不再显示"向量召回",避免误导)
_STAGE_MSGS_BY_MODE = {
    "kb": "理解完成,多路召回中(向量 + HyDE)…",
    "web": "理解完成,联网检索中…",
    "xhs": "理解完成,小红书检索中…",
}


def query_stream(question: str, history: list[dict] | None,
                 session_id: int | str = 0, message_id: int | str = 0,
                 search_mode: str = "kb") -> Iterator[tuple[str, object]]:
    """同步流式:yield 事件元组 (event, payload)。

    事件顺序: status* -> meta -> status -> delta* -> done | error
    - status 载荷:str(阶段提示:理解 / 召回 / 重排 / 生成,前端替换占位文案)
    - meta 载荷:{sources, confidence, low_confidence, threshold, meta}
    - delta 载荷:str(已清洗的增量答案文本,think 块已被 ThinkStreamFilter 剥掉)
    - done 载荷:str(完整答案)
    - error 载荷:str(错误说明)

    实现说明:llama-index 的 LLM 不发 LangChain 事件,astream_events 拿不到 token 级增量,
    所以分两段 —— 先跑检索子图(RETRIEVAL_GRAPH,不含 generate)出 meta,再在图外用
    LLMClient.stream_chat + ThinkStreamFilter 逐块产出 delta。SSE 的 event_stream()
    由 FastAPI 跑在线程池里(无事件循环),asyncio.run 驱动检索子图即可。

    阶段提示:检索子图改走 astream(stream_mode="updates"),节点一完成就推 status;
    终态由各节点增量按序 merge 得到(state 是无 reducer 的 TypedDict,merge 与
    ainvoke 终态一致)。astream 是异步迭代而本函数是同步生成器,用后台线程跑
    asyncio + queue 把 (event, payload) 递出来。
    """
    state = create_default_query_state(
        session_id=session_id,
        message_id=message_id,
        original_query=question,
        history=history or [],
        is_stream=True,
        search_mode=search_mode,
    )

    # 1. 检索子图逐节点推进:status 即时吐,终态最后从队列取
    evq: queue.Queue = queue.Queue()
    _EOS = object()  # 结束哨兵

    def _drive() -> None:
        async def _run() -> dict:
            merged: dict = {}
            # 本请求的搜索模式(用于按模式区分「召回中」阶段文案)
            req_mode = state.get("search_mode", "kb")
            async for update in RETRIEVAL_GRAPH.astream(state, stream_mode="updates"):
                for node, delta in (update or {}).items():
                    if isinstance(delta, dict):
                        merged.update(delta)
                    # preprocess 的阶段文案按模式区分;其余节点固定文案
                    msg = _STAGE_MSGS_BY_MODE.get(req_mode, _STAGE_MSGS["preprocess"]) if node == "preprocess" else _STAGE_MSGS.get(node)
                    if merged.get("intent") == "chitchat":
                        # 闲聊分支:preprocess 一完成就明说跳过检索;rrf/rerank 是空跑,
                        # 不刷"召回/重排"这类无意义的阶段文案
                        msg = "闲聊寒暄,跳过知识库检索…" if node == "preprocess" else None
                    if msg:
                        evq.put(("status", msg))
            # 初始 state 作为底层兜底并入:节点增量优先,未改写的键(如 search_mode /
            # session_id / original_query)用初始值 —— 让流式终态等价于 ainvoke 的完整 state,
            # 否则 meta 里 search_mode 等恒缺键、回退默认值,上报标签错误。
            for k, v in state.items():
                merged.setdefault(k, v)
            return merged

        try:
            evq.put(("final", asyncio.run(_run())))
        except Exception as e:
            evq.put(("error", f"检索失败: {e}"))
        finally:
            evq.put(_EOS)

    yield "status", "理解问题中(改写 + 意图识别)…"
    threading.Thread(target=_drive, daemon=True).start()
    final: dict | None = None
    while True:
        item = evq.get()
        if item is _EOS:
            break
        kind, payload = item
        if kind == "final":
            final = payload
            continue
        yield kind, payload  # status / error
        if kind == "error":
            return
    if final is None:
        return

    docs = final.get("reranked_docs") or []
    sources = _build_sources(docs)
    confidence = sources[0]["confidence"] if sources else None
    low_confidence = confidence is not None and confidence < Config.CONFIDENCE_THRESHOLD
    yield "meta", {
        "sources": sources,
        "confidence": confidence,
        "low_confidence": low_confidence,
        "threshold": Config.CONFIDENCE_THRESHOLD,
        "meta": {
            "intent": final.get("intent", ""),
            "rewritten": final.get("rewritten_query", ""),
            "search_mode": final.get("search_mode", "kb"),
            "raw_count": _raw_count(final),
            "recall_paths": _recall_paths(final),
        },
    }

    # 无资料:与 generate 节点的空资料行为保持一致,直接收场(闲聊分支除外 —— 它本来
    # 就不指望资料,空 docs 是预期,继续走下面的直接对话生成)
    intent = final.get("intent", "")
    if not docs and intent != "chitchat":
        yield "done", "我不知道,资料里没提到。"
        return

    # 2. 图外流式生成:stream_chat 产增量,ThinkStreamFilter 剥 think 块
    from app.core.llm import LLMClient, ThinkStreamFilter
    from app.rag.nodes.query_nodes import NodeGenerate

    yield "status", "回应中…" if intent == "chitchat" else "生成答案中…"

    query = final.get("rewritten_query") or question
    if intent == "chitchat":
        messages = NodeGenerate.build_chitchat_messages(query, state.get("history") or [])
        temperature, max_tokens = 0.5, 300
    else:
        messages = NodeGenerate.build_messages(query, docs)
        temperature, max_tokens = 0.2, 800
    stream = LLMClient(role="main").stream_chat(messages, temperature=temperature, max_tokens=max_tokens)
    flt = ThinkStreamFilter()
    parts: list[str] = []
    try:
        for chunk in stream:
            safe = flt.push(chunk)
            if safe:
                parts.append(safe)
                yield "delta", safe
        rest = flt.flush()
        if rest:
            parts.append(rest)
            yield "delta", rest
    except Exception as e:
        # 生成阶段不可恢复错误:推 error 收场,半成品答案不进 done(路由据此不落库)
        yield "error", f"答案生成失败: {e}"
        return
    yield "done", "".join(parts)


# ============== 兼容旧 API(供 chat.py 旧逻辑平滑过渡) ==============

class RAGPipeline:
    """薄壳:保留旧类名,内部直接调顶层函数,让 upload.py 的 get_pipeline() 不报错。"""

    def __init__(self):
        pass

    async def query(self, question: str, history: list[dict] | None = None,
                    session_id: int | str = 0, message_id: int | str = 0,
                    search_mode: str = "kb") -> dict:
        return await query(question, history, session_id, message_id, search_mode)

    def query_stream(self, question: str,
                     history: list[dict] | None = None,
                     session_id: int | str = 0, message_id: int | str = 0,
                     search_mode: str = "kb") -> Iterator[tuple[str, object]]:
        return query_stream(question, history, session_id, message_id, search_mode)

    async def ingest(self, file_path: str) -> dict:
        import uuid
        return await ingest(uuid.uuid4().hex, file_path)


_pipeline: RAGPipeline | None = None


def get_pipeline() -> RAGPipeline:
    """进程内 pipeline 单例(避免每次请求重载 BGE reranker 与 LangGraph 图)。"""
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGPipeline()
    return _pipeline
