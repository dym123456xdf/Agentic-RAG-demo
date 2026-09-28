"""MinIO 对象存储客户端 —— 单一职责:管理 MinIO 连接 + 桶 + 常用对象操作。

对象前缀命名约定:
    原文件:    uploads/<name>
    转换产物:  converted/<stem>/<stem>.md
              converted/<stem>/images/<file>.<ext>
              converted/<stem>/assets/<file>

桶策略:启动时确保桶存在并设置 public-read(便于直连调试与后端代理路由兼容)。

⚠️ MinIO 路径必须与前端 URL 契约 /converted/<stem>/... 一一对应(无 /auto/ 段);
   后端代理路由从 converted/<stem>/ 直接读,确保前端零改动。
"""
from __future__ import annotations

import io
import json
from typing import Iterator

from minio import Minio
from minio.error import S3Error

from app.core.config import Config

_client: Minio | None = None


# ============ 公共读策略 ============
_PUBLIC_READ_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"AWS": ["*"]},
            "Action": ["s3:GetObject"],
            "Resource": [f"arn:aws:s3:::{Config.MINIO_BUCKET}/*"],
        }
    ],
}


def _make_client() -> Minio:
    return Minio(
        endpoint=Config.MINIO_ENDPOINT,
        access_key=Config.MINIO_ACCESS_KEY,
        secret_key=Config.MINIO_SECRET_KEY,
        secure=Config.MINIO_SECURE,
    )


def get_minio_client() -> Minio:
    """进程内 MinIO 客户端单例。"""
    global _client
    if _client is None:
        _client = _make_client()
    return _client


def ensure_bucket() -> None:
    """启动钩子:桶不存在则创建,设置 public-read 策略。"""
    client = get_minio_client()
    bucket = Config.MINIO_BUCKET
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    client.set_bucket_policy(bucket, json.dumps(_PUBLIC_READ_POLICY))


# ============ 对象操作 ============

def put_object(key: str, data: bytes | io.BytesIO, length: int | None = None,
               content_type: str | None = None) -> None:
    """上传对象;length=0 抛 InvalidDataError。"""
    bucket = Config.MINIO_BUCKET
    if isinstance(data, (bytes, bytearray)):
        buf = io.BytesIO(data)
        size = len(data)
    else:
        buf = data
        size = length if length is not None else buf.getbuffer().nbytes
    if size == 0:
        raise ValueError(f"refuse to upload empty object: {bucket}/{key}")
    get_minio_client().put_object(
        bucket_name=bucket,
        object_name=key,
        data=buf,
        length=size,
        content_type=content_type,
    )


def delete_object(key: str) -> bool:
    """删除单个对象;不存在不报错。"""
    try:
        get_minio_client().remove_object(Config.MINIO_BUCKET, key)
        return True
    except S3Error as e:
        if e.code in ("NoSuchKey", "NoSuchObject"):
            return False
        raise


def delete_prefix(prefix: str) -> int:
    """删除指定前缀下全部对象(批量);返回实际删除数。"""
    client = get_minio_client()
    bucket = Config.MINIO_BUCKET
    count = 0
    # list_objects 不支持 prefix-only delete,用 list + remove_objects 批量
    objs = list(client.list_objects(bucket, prefix=prefix, recursive=True))
    for obj in objs:
        client.remove_object(bucket, obj.object_name)
        count += 1
    return count


def object_exists(key: str) -> bool:
    """对象是否存在。"""
    try:
        get_minio_client().stat_object(Config.MINIO_BUCKET, key)
        return True
    except S3Error as e:
        if e.code in ("NoSuchKey", "NoSuchObject"):
            return False
        raise


def get_object_stream(key: str) -> Iterator[bytes]:
    """流式读取对象;供后端代理路由使用,避免大文件一次性读入内存。

    用法:
        for chunk in get_object_stream("converted/报告/images/x.jpeg"):
            yield chunk

    兼容性:新版 urllib3 不再支持 resp.stream(chunk_size=...),改用 resp.read(chunk_size=...)
    分块循环,直到返回空 bytes 表示流结束。
    """
    resp = get_minio_client().get_object(Config.MINIO_BUCKET, key)
    chunk_size = 64 * 1024
    try:
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            yield chunk
    finally:
        resp.close()
        resp.release_conn()


def upload_directory(local_dir: str, prefix: str) -> int:
    """把本地目录整目录批量上传到 MinIO(对应 prefix);返回上传对象数。

    转换节点(NodeImportMilvus)用此函数把 MinerU staging 产物一次性上传 MinIO。
    """
    import os
    from pathlib import Path

    client = get_minio_client()
    bucket = Config.MINIO_BUCKET
    count = 0
    for root, _, files in os.walk(local_dir):
        for fname in files:
            fp = Path(root) / fname
            rel = fp.relative_to(local_dir).as_posix()
            key = f"{prefix.rstrip('/')}/{rel}"
            client.fput_object(bucket, key, str(fp))
            count += 1
    return count
