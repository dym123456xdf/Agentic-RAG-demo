"""问答路由 —— 单一职责:接收问题 + 会话标识,跑 RAG pipeline,返回答案 + 来源。

历史上下文由后端提供:调 pipeline 前从 MySQL 读当前会话最近 6 条消息拼 history,
前端不再传 history(请求体多余的 history 字段由 Pydantic 默认忽略)。
落库尽力而为:答案已生成后落库失败只记日志,不影响响应(design D4)。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.upload import get_pipeline
from app.core import db

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
    source: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
    meta: dict


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
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

    result = get_pipeline().query(req.question, history)

    try:
        db.add_messages(req.session_id, [
            {"role": "user", "content": req.question},
            {"role": "assistant", "content": result["answer"],
             "sources": result.get("sources"), "meta": result.get("meta")},
        ])
    except Exception as e:
        logger.warning(f"[chat] 问答落库失败(session={req.session_id}): {e}")

    return ChatResponse(**result)
