"""配置中心 —— 单一职责:从 .env 读取所有外部依赖配置,集中暴露给其它模块。

设计原则:
- 只做"读 + 校验 + 暴露",不发起任何网络请求,不在此处实例化客户端。
- 数值字段统一 int() / float() 强转,避免下游 Milvus / 重排组件拿到字符串崩溃。
- .env 不存在或缺关键字段时,启动即失败(快速失败,避免运行时才暴雷)。
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 解析项目根:app/core/config.py -> 项目根
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _need(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(
            f"环境变量 {key} 未配置。请检查项目根 .env 文件(模板见 open-ai-demo/.env)。"
        )
    return val


class Config:
    """统一配置入口,所有模块从这里取参数。"""

    # ====== LLM(对话 / 意图 / 改写 / 答案生成)======
    MINIMAX_API_KEY: str = _need("MINIMAX_API_KEY")
    MINIMAX_BASE_URL: str = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "MiniMax-M3")

    # ====== Embedding(向量入库 + 查询)======
    # embo-01 必填 GroupId(MiniMax 强制,丢在 URL query,不传 400)
    MINIMAX_GROUP_ID: str = _need("MINIMAX_GROUP_ID")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "embo-01")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "1536"))

    # ====== Milvus ======
    MILVUS_URI: str = os.getenv("MILVUS_URI", "http://localhost:19530")
    MILVUS_DB: str = os.getenv("MILVUS_DB", "rag_kb")
    MILVUS_COLLECTION: str = os.getenv("MILVUS_COLLECTION", "personal_kb")

    # ====== 检索 / 重排 ======
    TOP_K: int = int(os.getenv("TOP_K", "10"))
    RERANK_TOP_N: int = int(os.getenv("RERANK_TOP_N", "5"))
    # similarity_cutoff 是 Milvus COSINE distance 上限:
    # distance ∈ [0, 2],2.0 等于"全过",BGE 重排干全部精修;调低可粗筛
    SIMILARITY_CUTOFF: float = float(os.getenv("SIMILARITY_CUTOFF", "2.0"))
    RERANK_MODEL: str = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")

    # ====== 服务 / 上传 ======
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    UPLOAD_DIR: Path = PROJECT_ROOT / os.getenv("UPLOAD_DIR", "uploads")
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "50"))

    # ====== MinerU 文档解析(pipeline 后端,M4 16GB 友好)======
    # 总开关:True 时 PDF/DOCX/PPTX 走 minerU,False 时 fallback UnstructuredReader
    MINERU_ENABLED: bool = os.getenv("MINERU_ENABLED", "false").lower() == "true"
    # minerU 可执行文件路径(conda 环境下避免 PATH 找不到)
    MINERU_BIN: str = os.getenv("MINERU_BIN", "/opt/anaconda3/envs/rag/bin/mineru")
    # 转换出来的 markdown + 图片存放目录(项目根 converted/,可查可进仓)
    MINERU_OUTDIR: Path = PROJECT_ROOT / os.getenv("MINERU_OUTDIR", "converted")
    # minerU 单 PDF 解析超时(秒),避免卡死
    MINERU_TIMEOUT_S: int = int(os.getenv("MINERU_TIMEOUT_S", "600"))

    # 允许上传的文件后缀(白名单,避免任意文件被当作文档切分)
    ALLOWED_EXTS = {".pdf", ".md", ".markdown", ".docx", ".pptx", ".txt"}

    @classmethod
    def ensure_dirs(cls) -> None:
        """确保上传目录 + minerU 输出目录存在。"""
        cls.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        cls.MINERU_OUTDIR.mkdir(parents=True, exist_ok=True)


Config.ensure_dirs()
