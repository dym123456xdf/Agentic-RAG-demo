"""转换产物代理路由 —— 单一职责:把 /converted/<stem>/images/<file> 等请求从 MinIO 流式回放。

URL 契约与原本地 static mount 完全一致,前端零改动。

为什么用 FastAPI 代理而不是让前端直连 MinIO:
- 前端只看到 127.0.0.1:8011,直连 MinIO(9000)需要改前端 base URL;
- MinIO 即使配 public-read,跨域也得配 CORS,前端 CORS 配置也得改;
- 代理天然隐藏对象真实路径,便于后续切换到 S3/OSS。
"""
from __future__ import annotations

import mimetypes
from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.core import minio_client

router = APIRouter(tags=["converted"])


@router.get("/converted/{stem:path}")
async def converted_proxy(stem: str):
    """流式回放 MinIO converted/<stem> 对象。

    路径穿越防护:任何含 `..` 段或绝对路径前缀直接 404。
    """
    if ".." in stem.split("/"):
        raise HTTPException(404, "非法路径")
    if stem.startswith("/"):
        raise HTTPException(404, "非法路径")

    key = f"converted/{stem}"
    if not minio_client.object_exists(key):
        raise HTTPException(404, f"对象不存在: {key}")

    media_type = _guess_mime(key)
    return StreamingResponse(
        minio_client.get_object_stream(key),
        media_type=media_type,
    )


def _guess_mime(obj_path: str) -> str:
    """按后缀猜 MIME;md / jpeg / png / json 等常用后缀单独处理兜底。"""
    # mimetypes 拿常见类型
    mt, _ = mimetypes.guess_type(obj_path)
    if mt:
        return mt
    suffix = PurePosixPath(obj_path).suffix.lower()
    fallback = {
        ".md": "text/markdown; charset=utf-8",
        ".markdown": "text/markdown; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
        ".jpeg": "image/jpeg",
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".svg": "image/svg+xml",
    }
    return fallback.get(suffix, "application/octet-stream")
