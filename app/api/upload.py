"""上传路由 —— 单一职责:接收前端上传的文件 / 文件夹路径,触发入库 + 列已入库文件。

四个端点:
- POST /upload/files   multipart, 多个文件上传
- POST /upload/dir     JSON, 指定服务器上的目录路径,递归读
- GET  /upload/files   列出已入库文件(filename + chunks)
- POST /upload/clear   清空 collection(谨慎使用,删全部数据)

幂等:
- POST 任意一个入库端点,同名文件已在库中会跳过,不入 Milvus、不消耗 embedding。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import Config
from app.core.milvus_client import get_store
from app.rag.pipeline import RAGPipeline

router = APIRouter(prefix="/upload", tags=["upload"])

# 全局 pipeline 单例(进程内复用,避免每次请求都重载 BGE 模型)
_pipeline: RAGPipeline | None = None


def get_pipeline() -> RAGPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGPipeline()
    return _pipeline


@router.post("/files")
async def upload_files(files: list[UploadFile] = File(...)):  # noqa: B008
    """前端一次拖多个文件过来,落到 uploads/,入库。

    幂等:同名文件已存在直接跳过,只入库新文件。
    """
    if not files:
        raise HTTPException(400, "没收到文件")

    saved: list[str] = []
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in Config.ALLOWED_EXTS:
            raise HTTPException(400, f"不支持的文件格式: {ext}({f.filename})")

        # 防路径穿越:只用文件名,不接收子目录路径
        safe_name = Path(f.filename or "unnamed").name
        target = Config.UPLOAD_DIR / safe_name
        # 重复上传直接覆盖(后面入库时按文件名去重)
        with target.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        saved.append(safe_name)

    # 一次入库一批,只跑一次 embedding(对新文件)
    pipeline = get_pipeline()
    result = pipeline.ingest(str(Config.UPLOAD_DIR))
    return {"saved": saved, **result}


@router.post("/dir")
async def upload_dir(payload: dict):
    """前端传一个服务器能访问到的目录路径(支持 data/ 这种项目内置目录)。

    幂等:同目录内已在库中的文件直接跳过。
    """
    path = (payload or {}).get("path", "").strip()
    if not path:
        raise HTTPException(400, "需要传 path")

    p = Path(path)
    if not p.is_absolute():
        p = Path("/Users/daiyanmei/PycharmProjects/Agentic-RAG-demo") / path

    if not p.exists():
        raise HTTPException(404, f"路径不存在: {p}")

    pipeline = get_pipeline()
    result = pipeline.ingest(str(p))
    return {"ingested_from": str(p), **result}


@router.get("/files")
async def list_files():
    """列出已入库的文件 + 每个文件的 chunk 数。

    用于侧边栏展示 + 入库前的去重判定。
    """
    counts = get_store().list_sources()  # {filename: chunk_count}
    files = [
        {"name": name, "chunks": n}
        for name, n in sorted(counts.items())
    ]
    total_entities = sum(counts.values())
    return {
        "files": files,
        "file_count": len(files),
        "total_chunks": total_entities,
    }
