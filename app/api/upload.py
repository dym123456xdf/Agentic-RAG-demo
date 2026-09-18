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
from app.rag.loader import MINERU_CONVERTIBLE, convert_to_markdown, converted_md_path
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
async def upload_files(
    files: list[UploadFile] = File(...),  # noqa: B008
    convert_only: bool = False,
):
    """前端一次拖多个文件过来,落到 uploads/,入库。

    幂等:同名文件已存在直接跳过,只入库新文件。
    """
    if not files:
        raise HTTPException(400, "没收到文件")
    if convert_only and not Config.MINERU_ENABLED:
        raise HTTPException(400, "仅转换模式依赖 MinerU,请先设置 MINERU_ENABLED=true")

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

    # 仅转换模式:转 Markdown 落盘 converted/ 但不入库,先检查转换质量
    if convert_only:
        converted: list[str] = []
        for name in saved:
            p = Config.UPLOAD_DIR / name
            if p.suffix.lower() in MINERU_CONVERTIBLE:
                converted.append(str(convert_to_markdown(p)))
            else:
                # .md/.txt 本身就是可读文本,无需转换,直接返回源文件路径
                converted.append(str(p))
        return {
            "saved": saved,
            "converted": converted,
            "ingested": False,
            "note": "convert_only=true,仅转换未入库;检查 converted/*.md 无误后去掉参数重传即可入库",
        }

    # 一次入库一批,只跑一次 embedding(对新文件)
    pipeline = get_pipeline()
    result = pipeline.ingest(str(Config.UPLOAD_DIR))

    # 汇总本次入库链路中产生 / 复用的 MinerU 产物,方便前端展示 md 路径
    converted = []
    for name in saved:
        p = Config.UPLOAD_DIR / name
        if p.suffix.lower() in MINERU_CONVERTIBLE and converted_md_path(p).exists():
            converted.append(str(converted_md_path(p)))

    return {"saved": saved, "converted": converted, **result}


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
    """列出已入库的文件 + 每个文件的 chunk 数 + 是否有 MinerU 转换产物。

    用于管理页展示 + 入库前的去重判定。
    """
    counts = get_store().list_sources()  # {filename: chunk_count}
    files = [
        {
            "name": name,
            "chunks": n,
            "has_converted": _has_converted(name),
        }
        for name, n in sorted(counts.items())
    ]
    total_entities = sum(counts.values())
    return {
        "files": files,
        "file_count": len(files),
        "total_chunks": total_entities,
        "mineru_enabled": Config.MINERU_ENABLED,
    }


def _has_converted(name: str) -> bool:
    """该入库文件是否有对应的 MinerU 转换产物(converted/<stem>/<stem>.md)。"""
    if not Config.MINERU_ENABLED:
        return False
    if Path(name).suffix.lower() not in MINERU_CONVERTIBLE:
        return False
    return converted_md_path(Config.UPLOAD_DIR / name).exists()


@router.get("/converted/{name}")
async def get_converted(name: str):
    """读取 MinerU 转换产物 Markdown,供人工核对转换质量。

    入参 name 为原文件名(含后缀,如 `报告.pdf`),经 converted_md_path 定位到
    converted/<stem>/<stem>.md。

    安全:name 只取 basename 且后缀必须在 MINERU_CONVERTIBLE 白名单内;
    产物路径由 converted_md_path 拼装(stem 不会再带分隔符),天然限定在
    MINERU_OUTDIR 内 —— 防路径穿越。
    """
    safe = Path(name).name
    if safe != name or "/" in name or "\\" in name:
        raise HTTPException(404, "非法文件名")
    if Path(safe).suffix.lower() not in MINERU_CONVERTIBLE:
        raise HTTPException(404, "非法文件名")
    target = converted_md_path(Config.UPLOAD_DIR / safe)
    if not target.is_file():
        raise HTTPException(404, f"转换产物不存在: {safe}")
    return {"name": safe, "content": target.read_text(encoding="utf-8", errors="ignore")}
