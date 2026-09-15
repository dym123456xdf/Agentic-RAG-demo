"""FastAPI 入口 —— 单一职责:组装 app 实例 + 挂路由 + 挂静态页。

运行:
    conda run -n rag uvicorn main:app --host 127.0.0.1 --port 8000 --reload
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api import upload, chat
from app.core.config import Config

# 项目根 / 静态页
ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"

app = FastAPI(title="个人知识库 RAG", version="0.1.0")

# 业务路由
app.include_router(upload.router)
app.include_router(chat.router)


# 启动时打一行,确认服务起得来
@app.on_event("startup")
def _startup():
    print(f"[startup] 知识库服务起在 http://{Config.HOST}:{Config.PORT}")
    print(f"[startup] 上传目录: {Config.UPLOAD_DIR}")
    print(f"[startup] Milvus: {Config.MILVUS_URI}  db={Config.MILVUS_DB}  collection={Config.MILVUS_COLLECTION}")


# 首页 + 静态资源
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    idx = STATIC_DIR / "index.html"
    if idx.exists():
        return FileResponse(idx)
    return {"msg": "static/index.html missing"}