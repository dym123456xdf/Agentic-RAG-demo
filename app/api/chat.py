"""问答路由 —— 单一职责:接收问题 + 对话历史,跑 RAG pipeline,返回答案 + 来源。

前端用 SSE 流式 / 一次性返回都可以,这里先一次性返回(简单稳定)。
"""
from __future__ import annotations

from typing import List, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.upload import get_pipeline

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str
    history: Optional[List[ChatMessage]] = None


class SourceItem(BaseModel):
    index: int
    content: str
    score: float
    source: str


class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceItem]
    meta: Dict


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    history = [m.model_dump() for m in (req.history or [])]
    pipeline = get_pipeline()
    result = pipeline.query(req.question, history)
    return ChatResponse(**result)