"""MySQL 存储层 —— 单一职责:问答历史(sessions / messages 两表)的连接管理与读写。

设计原则:
- 懒加载:import 不连接,首次 get_conn() 才连 —— MySQL 不可用时问答仍可降级运行(design D4)。
- 单连接 + ping(reconnect=True):demo 单用户负载足够(design D1)。
- 启动自建:首次连接成功即 CREATE DATABASE / TABLE IF NOT EXISTS,沿用 milvus_client"启动即可用"模式。
- 落库尽力而为由调用方(chat 路由)负责,本模块只抛异常不打日志。
"""
from __future__ import annotations

import json
from typing import Any

import pymysql

from app.core.config import Config

_conn: pymysql.connections.Connection | None = None
_schema_ready = False


def _connect() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=Config.MYSQL_HOST,
        port=Config.MYSQL_PORT,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def get_conn() -> pymysql.connections.Connection:
    """进程内单连接;断线自动重连,首次连接成功时自建库表。MySQL 不可用时抛异常。

    注意:_ensure_schema 只在首次跑(建库 + USE + 建表);ping(reconnect=True) 后
    若真的重连,_schema_ready 仍为 True,但 USE 已失效。所以此处无条件再 USE 一次,
    保证当前连接指向 Config.MYSQL_DATABASE,避免重连后报 1046 No database selected。
    """
    global _conn, _schema_ready
    if _conn is None:
        _conn = _connect()
    _conn.ping(reconnect=True)
    if not _schema_ready:
        _ensure_schema(_conn)
        _schema_ready = True
    # 重连后 USE 状态会丢失,每次都显式切一次(轻量、幂等)
    with _conn.cursor() as cur:
        cur.execute(f"USE `{Config.MYSQL_DATABASE}`")
    return _conn


def _ensure_schema(conn: pymysql.connections.Connection) -> None:
    db = Config.MYSQL_DATABASE
    with conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db}` CHARACTER SET utf8mb4")
        cur.execute(f"USE `{db}`")
        cur.execute(
            """CREATE TABLE IF NOT EXISTS sessions(
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS messages(
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            session_id BIGINT NOT NULL,
            role ENUM('user','assistant') NOT NULL,
            content MEDIUMTEXT NOT NULL,
            sources JSON NULL,
            meta JSON NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_session (session_id, id),
            CONSTRAINT fk_msg_session FOREIGN KEY (session_id)
                REFERENCES sessions(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
        )


def _dump(value: Any) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def _loads(value: Any) -> Any:
    if value is None or isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


# ============== 会话 DAO ==============

def create_session(title: str) -> dict:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO sessions(title) VALUES(%s)", (title[:200],))
        cur.execute("SELECT id, title, created_at, updated_at FROM sessions WHERE id=%s", (cur.lastrowid,))
        return cur.fetchone()


def list_sessions() -> list[dict]:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT s.id, s.title, s.created_at, s.updated_at,
                      COUNT(m.id) AS message_count
               FROM sessions s LEFT JOIN messages m ON m.session_id = s.id
               GROUP BY s.id ORDER BY s.updated_at DESC"""
        )
        return cur.fetchall()


def get_session(session_id: int) -> dict | None:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id, title, created_at, updated_at FROM sessions WHERE id=%s", (session_id,))
        return cur.fetchone()


def delete_session(session_id: int) -> None:
    conn = get_conn()
    with conn.cursor() as cur:
        # messages 有 ON DELETE CASCADE,删会话即删消息
        cur.execute("DELETE FROM sessions WHERE id=%s", (session_id,))


def touch_session(session_id: int) -> None:
    """落库消息后刷新会话活跃时间,保证列表按最近活跃倒序。"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("UPDATE sessions SET updated_at=NOW() WHERE id=%s", (session_id,))


# ============== 消息 DAO ==============

def add_messages(session_id: int, rows: list[dict]) -> None:
    """批量落库。rows: [{"role": "user|assistant", "content": str,
    "sources": list|None, "meta": dict|None}]"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO messages(session_id, role, content, sources, meta) VALUES(%s,%s,%s,%s,%s)",
            [
                (session_id, r["role"], r["content"], _dump(r.get("sources")), _dump(r.get("meta")))
                for r in rows
            ],
        )
    touch_session(session_id)


def _row_to_message(row: dict) -> dict:
    return {
        "id": row["id"],
        "role": row["role"],
        "content": row["content"],
        "sources": _loads(row.get("sources")),
        "meta": _loads(row.get("meta")),
        "created_at": row["created_at"],
    }


def recent_messages(session_id: int, n: int) -> list[dict]:
    """最近 n 条,按时间正序返回(给查询改写当 history 上下文)。"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT * FROM (SELECT * FROM messages WHERE session_id=%s ORDER BY id DESC LIMIT %s) t ORDER BY id",
            (session_id, n),
        )
        return [_row_to_message(r) for r in cur.fetchall()]


def list_messages(session_id: int) -> list[dict]:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM messages WHERE session_id=%s ORDER BY id", (session_id,))
        return [_row_to_message(r) for r in cur.fetchall()]


def clear_messages(session_id: int) -> None:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM messages WHERE session_id=%s", (session_id,))
