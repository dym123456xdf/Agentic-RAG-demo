"""会话路由 —— 单一职责:问答会话的 CRUD 与消息查询/清空。

五个端点:
- POST   /sessions                创建会话(可选 title,默认"新会话")
- GET    /sessions                列出全部会话(按最近活跃倒序,含消息数)
- DELETE /sessions/{sid}          删除会话(消息级联删除)
- GET    /sessions/{sid}/messages 按时间正序返回该会话全部消息(含 sources/meta)
- POST   /sessions/{sid}/clear    清空该会话消息但保留会话

MySQL 不可用时统一返回 503(问答主链路不受影响,见 design D4)。
"""
from __future__ import annotations

import pymysql
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core import db

router = APIRouter(prefix="/sessions", tags=["sessions"])

DEFAULT_TITLE = "新会话"


class SessionCreate(BaseModel):
    title: str | None = None


def _not_found(sid: int):
    return HTTPException(404, f"会话不存在: {sid}")


@router.post("")
async def create_session(payload: SessionCreate | None = None):
    title = (payload.title if payload else None) or DEFAULT_TITLE
    try:
        return db.create_session(title)
    except pymysql.MySQLError:
        raise HTTPException(503, "MySQL 不可用,请检查数据库服务")


@router.get("")
async def list_sessions():
    try:
        return {"sessions": db.list_sessions()}
    except pymysql.MySQLError:
        raise HTTPException(503, "MySQL 不可用,请检查数据库服务")


def _require_session(sid: int) -> dict:
    session = db.get_session(sid)
    if session is None:
        raise _not_found(sid)
    return session


@router.delete("/{sid}")
async def delete_session(sid: int):
    try:
        _require_session(sid)
        db.delete_session(sid)
        return {"deleted": sid}
    except HTTPException:
        raise
    except pymysql.MySQLError:
        raise HTTPException(503, "MySQL 不可用,请检查数据库服务")


@router.get("/{sid}/messages")
async def list_messages(sid: int):
    try:
        _require_session(sid)
        return {"session_id": sid, "messages": db.list_messages(sid)}
    except HTTPException:
        raise
    except pymysql.MySQLError:
        raise HTTPException(503, "MySQL 不可用,请检查数据库服务")


@router.post("/{sid}/clear")
async def clear_session(sid: int):
    try:
        _require_session(sid)
        db.clear_messages(sid)
        return {"cleared": sid}
    except HTTPException:
        raise
    except pymysql.MySQLError:
        raise HTTPException(503, "MySQL 不可用,请检查数据库服务")
