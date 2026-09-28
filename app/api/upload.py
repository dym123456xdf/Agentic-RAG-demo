"""上传路由 —— 单一职责:接收文件上传 → MinIO 落桶 → 触发入库图;列已入库 + 删除 + 清空。

四个端点:
- POST /upload/files       multipart 多文件上传
- GET  /upload/files       列出已入库文件(filename + chunks + has_converted)
- DELETE /upload/files/{name}  联动清除 Milvus + MinIO(原文件 + 转换产物)
- POST /upload/clear       清空 collection(drop + 重建)

幂等:同名文件已在库中(Milvus doc_name 命中)时后端跳过入库(前端预检之外的第二道
防线);CLAUDE.md 硬约束「同名文件重传不入库,改内容不会更新索引」由后端兜底保证。
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core import milvus_hybrid, minio_client
from app.core.config import Config
from app.rag.pipeline import ingest

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/files")
async def upload_files(files: list[UploadFile] = File(...)):  # noqa: B008
    """前端一次拖多个文件过来 → MinIO uploads/<name> → 触发入库图。

    幂等:同名文件已在库中(Milvus doc_name 命中)则跳过入库、不重复消耗 embedding
    (CLAUDE.md 硬约束:同名文件重传不入库,改内容不会更新索引);MinIO 原文件仍覆盖为最新。
    前端预检拦截只是第一道防线,API 层这里是兜底。
    """
    if not files:
        raise HTTPException(400, "没收到文件")

    saved: list[str] = []
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in Config.ALLOWED_EXTS:
            raise HTTPException(400, f"不支持的文件格式: {ext}({f.filename})")
        safe_name = Path(f.filename or "unnamed").name
        # 防路径穿越
        if "/" in f.filename or "\\" in f.filename or safe_name != f.filename:
            raise HTTPException(400, f"非法文件名: {f.filename}")

        data = await f.read()
        minio_key = f"uploads/{safe_name}"
        try:
            minio_client.put_object(minio_key, data, length=len(data))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        saved.append(safe_name)

    # 后端幂等兜底:已在库中的同名文件直接跳过(前端预检之外的路径,如 curl)
    existing = milvus_hybrid.list_doc_names()

    # 入库:每个文件独立触发入库图
    results = []
    for name in saved:
        if name in existing:
            results.append({"name": name, "skipped": True})
            continue
        try:
            r = await ingest(task_id=f"upload-{name}", file_path=f"uploads/{name}")
            results.append({"name": name, **r})
        except Exception as e:
            logger.exception(f"[upload] {name} 入库失败")
            results.append({"name": name, "error": str(e)})

    chunks_ingested = sum(r.get("chunks_ingested", 0) for r in results if "chunks_ingested" in r)
    total_entities = milvus_hybrid.list_doc_names()
    total_chunks = sum(total_entities.values())

    return {
        "saved": saved,
        "ingested": [{"name": r.get("name"), "chunks": r.get("chunks_ingested", 0),
                       "uploaded_objects": r.get("uploaded_objects", 0),
                       "skipped": r.get("skipped", False),
                       "error": r.get("error")}
                      for r in results],
        "chunks_ingested": chunks_ingested,
        "total_entities": total_chunks,
        "total_chunks": total_chunks,
    }


@router.get("/files")
async def list_files():
    """列出已入库文件 + chunk 数 + 是否有 MinerU 转换产物(MinIO 端判断)。"""
    counts = milvus_hybrid.list_doc_names()  # {filename: chunk_count}
    files = [
        {
            "name": name,
            "chunks": n,
            "has_converted": _has_converted(name),
        }
        for name, n in sorted(counts.items())
    ]
    total_chunks = sum(counts.values())
    return {
        "files": files,
        "file_count": len(files),
        "total_chunks": total_chunks,
        "mineru_enabled": Config.MINERU_ENABLED,
    }


def _has_converted(name: str) -> bool:
    """该文件是否有对应的 MinerU 转换产物(MinIO `converted/<stem>/<stem>.md`)。"""
    if not Config.MINERU_ENABLED:
        return False
    from app.rag.loader_compat import MINERU_CONVERTIBLE  # 延迟引入兼容
    if Path(name).suffix.lower() not in MINERU_CONVERTIBLE:
        return False
    stem = Path(name).stem
    return minio_client.object_exists(f"converted/{stem}/{stem}.md")


@router.delete("/files/{name}")
async def delete_file(name: str):
    """三处联动删除:Milvus + MinIO uploads/<name> + MinIO converted/<stem>/ 前缀。

    任一处缺失不报错(支持脏数据清理)。
    """
    safe = Path(name).name
    if safe != name or "/" in name or "\\" in name:
        raise HTTPException(404, "非法文件名")
    if Path(safe).suffix.lower() not in Config.ALLOWED_EXTS:
        raise HTTPException(404, "非法文件名")

    chunks_removed = milvus_hybrid.delete_by_doc_name(safe)

    upload_key = f"uploads/{safe}"
    upload_gone_before = not minio_client.object_exists(upload_key)
    if not upload_gone_before:
        minio_client.delete_object(upload_key)

    stem = Path(safe).stem
    converted_prefix = f"converted/{stem}/"
    converted_gone_before = (
        not any(
            minio_client.get_minio_client().list_objects(
                Config.MINIO_BUCKET, prefix=converted_prefix, recursive=False
            )
        )
    )
    converted_removed = 0
    if not converted_gone_before:
        converted_removed = minio_client.delete_prefix(converted_prefix)

    if chunks_removed == 0 and upload_gone_before and converted_gone_before:
        raise HTTPException(404, f"不在库中: {safe}")

    print(
        f"[upload] 删除 {safe}: Milvus {chunks_removed} chunk,"
        f" uploads={'删' if not upload_gone_before else '无'},"
        f" converted={'删 ' + str(converted_removed) if converted_removed else '无'}"
    )
    return {"deleted": safe, "chunks_removed": chunks_removed}


@router.post("/clear")
async def clear_all():
    """清空 collection(drop + 重建空 schema);客户端慎用。"""
    milvus_hybrid.drop_collection()
    milvus_hybrid.ensure_collection(dim=Config.EMBEDDING_DIM)
    return {"cleared": True}


@router.get("/converted/{name}")
async def get_converted(name: str):
    """读取 MinerU 转换产物 md,从 MinIO 流式回放(供人工核对)。"""
    safe = Path(name).name
    if safe != name or "/" in name or "\\" in name:
        raise HTTPException(404, "非法文件名")
    from app.rag.loader_compat import MINERU_CONVERTIBLE
    if Path(safe).suffix.lower() not in MINERU_CONVERTIBLE:
        raise HTTPException(404, "非法文件名")

    stem = Path(safe).stem
    md_key = f"converted/{stem}/{stem}.md"
    if not minio_client.object_exists(md_key):
        raise HTTPException(404, f"转换产物不存在: {safe}")
    # 流式拼接后一次性返回(转换产物 md 通常 KB~MB 级)
    buf = io.BytesIO()
    for chunk in minio_client.get_object_stream(md_key):
        buf.write(chunk)
    return {"name": safe, "content": buf.getvalue().decode("utf-8", errors="ignore")}
