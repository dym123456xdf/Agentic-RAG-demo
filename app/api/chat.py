"""问答路由 —— 单一职责:接收问题 + 会话标识,跑 RAG pipeline,返回答案 + 来源。

两个出口:
- POST /chat       非流式:等全量答案 + 来源 + meta
- POST /chat/stream 流式(SSE):status* -> meta -> status -> delta* -> done | error 逐事件推,
  检索各节点完成即推 status(阶段提示),检索一完成就推 meta(来源可见),
  答案逐字流出,前端感知延迟大降。

历史上下文由后端提供:调 pipeline 前从 MySQL 读当前会话最近 6 条消息拼 history,
前端不再传 history(请求体多余的 history 字段由 Pydantic 默认忽略)。
落库尽力而为:答案已生成后落库失败只记日志,不影响响应(design D4);
流式只在 done 事件后落库,error 路径不落库(半成品答案会污染后续改写上下文)。
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core import db
from app.core.config import Config
from app.rag.pipeline import get_pipeline

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/chat", tags=["chat"])

HISTORY_WINDOW = 3  # 与 pre_query.HISTORY_WINDOW 对齐:最近 3 轮(user+assistant 算一对)


class ChatRequest(BaseModel):
    question: str
    session_id: int


class SourceItem(BaseModel):
    index: int
    content: str
    score: float
    # 0-1 置信度(sigmoid(重排 logit));旧数据 / 未经 post 的节点为 null,前端隐藏
    confidence: float | None
    source: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
    meta: dict


def _resolve(req: ChatRequest) -> tuple[dict, list[dict[str, str]]]:
    """两个出口共用的校验 + 历史读取:会话不存在 404、空问题 400、MySQL 挂 503。"""
    if not req.question.strip():
        raise HTTPException(400, "问题不能为空")

    try:
        session = db.get_session(req.session_id)
    except Exception:
        raise HTTPException(503, "MySQL 不可用,请检查数据库服务")
    if session is None:
        raise HTTPException(404, f"会话不存在: {req.session_id}")

    # 从存储读当前会话最近几轮当改写上下文(单一数据源在服务端)
    try:
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in db.recent_messages(req.session_id, HISTORY_WINDOW * 2)
        ]
    except Exception:
        history = []  # 历史读取失败按首轮处理,不阻断问答
    return session, history


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    _, history = _resolve(req)

    result = await get_pipeline().query(req.question, history)
    sources = result.get("sources") or []
    # 与流式接口落库形态对齐:历史回溯需要 meta 低置信度三字段才能复现前端提示,
    # 否则非流式接口的记录在管理页永远不显示友情提示条(与流式不一致)。
    top_confidence = sources[0].get("confidence") if sources else None
    low_confidence = top_confidence is not None and top_confidence < Config.CONFIDENCE_THRESHOLD
    persisted_meta = dict(result.get("meta") or {})
    persisted_meta.update({
        "confidence": top_confidence,
        "low_confidence": low_confidence,
        "threshold": Config.CONFIDENCE_THRESHOLD,
    })

    try:
        db.add_messages(req.session_id, [
            {"role": "user", "content": req.question},
            {"role": "assistant", "content": result["answer"],
             "sources": sources, "meta": persisted_meta},
        ])
    except Exception as e:
        logger.warning(f"[chat] 问答落库失败(session={req.session_id}): {e}")

    return ChatResponse(**result)


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """流式问答:校验失败按普通 HTTP 返回(400/404/503),进流后错误用 error 事件。"""
    _, history = _resolve(req)

    def event_stream():
        meta_payload: dict | None = None
        full_answer = ""
        for event, payload in get_pipeline().query_stream(req.question, history):
            if event == "meta":
                meta_payload = payload  # type: ignore[assignment]
                frame = {"type": event, **payload}  # type: ignore[misc]
            elif event == "status":
                frame = {"type": event, "text": str(payload)}
            elif event == "delta":
                full_answer += str(payload)
                frame = {"type": event, "text": str(payload)}
            elif event == "done":
                full_answer = str(payload)
                frame = {"type": event, "answer": full_answer}
                # 只在 done 落库:error 路径的半成品答案不进历史。
                # 落库 meta 在调试 meta 之上叠加置信度三字段,历史回溯才能复现低置信度提示。
                persisted_meta = dict(meta_payload.get("meta") or {}) if meta_payload else {}
                if meta_payload:
                    persisted_meta.update({
                        "confidence": meta_payload.get("confidence"),
                        "low_confidence": meta_payload.get("low_confidence"),
                        "threshold": meta_payload.get("threshold"),
                    })
                try:
                    db.add_messages(req.session_id, [
                        {"role": "user", "content": req.question},
                        {"role": "assistant", "content": full_answer,
                         "sources": meta_payload.get("sources") if meta_payload else None,
                         "meta": persisted_meta or None},
                    ])
                except Exception as e:
                    logger.warning(f"[chat/stream] 问答落库失败(session={req.session_id}): {e}")
            elif event == "error":
                frame = {"type": event, "message": str(payload)}
            else:  # pragma: no cover - 防御未知事件名
                continue
            yield f"data: {json.dumps(frame, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
