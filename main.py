"""FastAPI 入口 —— 单一职责:组装 app 实例 + 挂路由 + 启动钩子(保证 MinIO 桶 / Milvus collection 就绪)。

运行:
    conda run -n rag uvicorn main:app --host 127.0.0.1 --port 8011 --reload

启动钩子:
1. ensure_dirs()(MinerU staging 目录)
2. ensure_bucket()(MinIO 桶 + public-read 策略)
3. ensure_collection()(Milvus hybrid collection)

企业版变化:
- 移除原 app.mount("/converted", StaticFiles(...))—— 由 app/api/converted.py 代理路由接管
- upload.py 内部走 MinIO,本地 uploads/ 仅作 MinerU 子进程临时目录
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api import upload, chat, sessions, converted, config
from app.core.config import Config
from app.core import minio_client, milvus_hybrid

# root logger 无 handler 时节点 INFO 日志全丢(basicConfig 只在首次调用生效,uvicorn 自带的
# handler 只覆盖它自己的 "uvicorn.*" logger),这里兜底配一条,保证入库/查询图日志可见
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

# 项目根 / 静态页
ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"

app = FastAPI(title="个人知识库 RAG(企业版)", version="0.2.0")

# 业务路由
app.include_router(upload.router)
app.include_router(chat.router)
app.include_router(sessions.router)
# 转换产物代理路由(URL 契约 /converted/<stem>/... 与原本地 mount 完全一致)
app.include_router(converted.router)
# 部署级主开关查询(前端搜索模式下拉按可用性过滤选项)
app.include_router(config.router)


@app.on_event("startup")
def _startup():
    print(f"[startup] 知识库服务起在 http://{Config.HOST}:{Config.PORT}")
    print(f"[startup] MinIO: {Config.MINIO_ENDPOINT} bucket={Config.MINIO_BUCKET}")
    print(f"[startup] Milvus: {Config.MILVUS_URI} db={Config.MILVUS_DB} collection={Config.MILVUS_COLLECTION}")
    # 启动期一次性初始化外部服务:MinIO 桶 + Milvus collection schema
    minio_client.ensure_bucket()
    milvus_hybrid.ensure_collection(dim=Config.EMBEDDING_DIM)


# 首页 + 静态资源
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    idx = STATIC_DIR / "index.html"
    if idx.exists():
        return FileResponse(idx)
    return {"msg": "static/index.html missing"}
