"""配置中心 —— 单一职责:从 .env 读取所有外部依赖配置,集中暴露给其它模块。

设计原则:
- 只做"读 + 校验 + 暴露",不发起任何网络请求,不在此处实例化客户端。
- 数值字段统一 int() / float() 强转,避免下游 Milvus / 重排组件拿到字符串崩溃。
- .env 不存在或缺关键字段时,启动即失败(快速失败,避免运行时才暴雷)。

升级到企业版后:
- Embedding 改为本地 BGE-M3(FlagEmbedding),EMBEDDING_PROVIDER 只剩 "bge-m3" 一档;
  旧 embo-01 / embedding-3 双供应商已废弃,切换 provider = 必须清空 Milvus collection 重建。
- LLM 维持现有 minimax / glm 双 provider 协议,llm.py 不动。
- 新增 MinIO / MCP / 断崖检测 / HyDE 启用 / Web 启用 等配置项,缺失时启动即失败。
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
            f"环境变量 {key} 未配置。请检查项目根 .env 文件。"
        )
    return val


def _bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, "true" if default else "false").lower() == "true"


class Config:
    """统一配置入口,所有模块从这里取参数。"""

    # ====== LLM(对话 / 意图 / 改写 / 答案生成)======
    # provider 切换:minimax(默认)/ glm(智谱 / Z.ai),两者都是 OpenAI 兼容协议
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "minimax").strip().lower()
    MINIMAX_API_KEY: str = _need("MINIMAX_API_KEY")
    MINIMAX_BASE_URL: str = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "MiniMax-M3")

    # ====== GLM(智谱开放平台 / Z.ai,仅 LLM_PROVIDER=glm 时必填)======
    GLM_API_KEY: str = os.getenv("GLM_API_KEY", "")
    GLM_BASE_URL: str = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    GLM_MODEL: str = os.getenv("GLM_MODEL", "glm-5.3-flash")
    GLM_FAST_MODEL: str = os.getenv("GLM_FAST_MODEL", "glm-4.7-flash")

    # ====== Agnes(apihub.agnes-ai.com,OpenAI 兼容,仅 LLM_PROVIDER=agnes 时必填)======
    # 文本档:agnes-3.0-flash;图片档 agnes-image-2.1-flash 不走对话链路
    AGNES_API_KEY: str = os.getenv("AGNES_API_KEY", "")
    AGNES_BASE_URL: str = os.getenv("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
    AGNES_MODEL: str = os.getenv("AGNES_MODEL", "agnes-3.0-flash")

    # ====== Embedding(向量入库 + 查询)======
    # 企业版:统一本地 BGE-M3(FlagEmbedding),产出 dense(1024) + sparse 双向量。
    # 旧 embo-01 / embedding-3 双供应商已废弃 —— 切换 provider 必清空 Milvus 重建。
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "bge-m3").strip().lower()
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "1024"))
    BGE_M3_MODEL: str = os.getenv("BGE_M3_MODEL", "BAAI/bge-m3")
    BGE_M3_DEVICE: str = os.getenv("BGE_M3_DEVICE", "mps")  # mps / cuda / cpu

    # ====== Milvus(hybrid dense+sparse collection)======
    MILVUS_URI: str = os.getenv("MILVUS_URI", "http://localhost:19530")
    MILVUS_DB: str = os.getenv("MILVUS_DB", "rag_kb")
    MILVUS_COLLECTION: str = os.getenv("MILVUS_COLLECTION", "rag_kb_chunks")
    # 旧 schema(单 dense 字段)检测到时是否自动 drop 重建;默认 true(旧数据视为 demo)
    AUTO_REBUILD_SCHEMA: bool = _bool("AUTO_REBUILD_SCHEMA", True)

    # ====== MySQL(问答历史持久化,保留)======
    MYSQL_HOST: str = _need("MYSQL_HOST")
    MYSQL_PORT: int = int(_need("MYSQL_PORT"))
    MYSQL_USER: str = _need("MYSQL_USER")
    MYSQL_PASSWORD: str = _need("MYSQL_PASSWORD")
    MYSQL_DATABASE: str = _need("MYSQL_DATABASE")

    # ====== 检索 / 重排 / 断崖检测 ======
    TOP_K: int = int(os.getenv("TOP_K", "20"))
    RERANK_TOP_N: int = int(os.getenv("RERANK_TOP_N", "5"))
    SIMILARITY_CUTOFF: float = float(os.getenv("SIMILARITY_CUTOFF", "2.0"))
    RERANK_MODEL: str = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
    # 低置信度友情提示阈值(0-1):重排 logit 经 sigmoid 归一后与它比,< 阈值时首页显示提示。
    CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))
    # 断崖检测双阈值(0-1 标度,作用于 BGE-reranker score)
    RERANK_GAP_ABS: float = float(os.getenv("RERANK_GAP_ABS", "1.0"))
    RERANK_GAP_RATIO: float = float(os.getenv("RERANK_GAP_RATIO", "0.3"))
    RERANK_MIN_TOPK: int = int(os.getenv("RERANK_MIN_TOPK", "3"))
    RERANK_MAX_TOPK: int = int(os.getenv("RERANK_MAX_TOPK", "10"))
    # RRF 倒数排名融合参数
    RRF_K: int = int(os.getenv("RRF_K", "60"))

    # ====== MinIO 对象存储 ======
    MINIO_ENDPOINT: str = _need("MINIO_ENDPOINT")
    MINIO_ACCESS_KEY: str = _need("MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY: str = _need("MINIO_SECRET_KEY")
    MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "rag-kb")
    MINIO_SECURE: bool = _bool("MINIO_SECURE", False)

    # ====== MCP 自建服务 ======
    MCP_SERVER_HOST: str = os.getenv("MCP_SERVER_HOST", "127.0.0.1")
    MCP_SERVER_PORT: int = int(os.getenv("MCP_SERVER_PORT", "8765"))
    BRAVE_SEARCH_API_KEY: str = os.getenv("BRAVE_SEARCH_API_KEY", "")

    # ====== 小红书 MCP(外部独立部署服务,Streamable HTTP)======
    # xiaohongshu-mcp 由用户自行下载二进制 / Docker 部署(默认 :18060/mcp)并扫码登录,
    # 生命周期与本服务解耦:启动期只校验 URL 非空,不做网络探测,运行期失败降级空路。
    XHS_MCP_ENABLED: bool = _bool("XHS_MCP_ENABLED", False)
    XHS_MCP_URL: str = os.getenv("XHS_MCP_URL", "http://127.0.0.1:18060/mcp")
    XHS_MCP_TOKEN: str = os.getenv("XHS_MCP_TOKEN", "")  # 可选 Bearer;留空不携带鉴权头
    XHS_SEARCH_LIMIT: int = int(os.getenv("XHS_SEARCH_LIMIT", "5"))

    # ====== 特性开关 ======
    # HyDE 假设文档检索启用(factual / explanatory 意图下挂载)
    HYDE_ENABLED: bool = _bool("HYDE_ENABLED", True)
    # Web 搜索启用(factual 意图下挂载,需 BRAVE_SEARCH_API_KEY)
    WEB_SEARCH_ENABLED: bool = _bool("WEB_SEARCH_ENABLED", False)

    # ====== 服务 / 上传 ======
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "50"))
    # 旧 UPLOAD_DIR 字段保留兼容:写入路径走 MinIO 后,本地仅作 MinerU 子进程的 staging
    UPLOAD_DIR: Path = PROJECT_ROOT / os.getenv("UPLOAD_DIR", "uploads")

    # ====== MinerU 文档解析 ======
    MINERU_ENABLED: bool = _bool("MINERU_ENABLED", False)
    MINERU_BIN: str = os.getenv("MINERU_BIN", "/opt/anaconda3/envs/rag/bin/mineru")
    MINERU_KIT_BIN: str = os.getenv(
        "MINERU_KIT_BIN",
        str(Path(MINERU_BIN).with_name("mineru-kit")) if MINERU_BIN else "/opt/anaconda3/envs/rag/bin/mineru-kit",
    )
    # MinerU 转换产物落盘 staging 目录(转换后立即上传 MinIO + 删除 staging)
    MINERU_OUTDIR: Path = PROJECT_ROOT / os.getenv("MINERU_OUTDIR", "converted")
    MINERU_TIMEOUT_S: int = int(os.getenv("MINERU_TIMEOUT_S", "600"))

    # 允许上传的文件后缀(白名单)
    ALLOWED_EXTS = {".pdf", ".md", ".markdown", ".docx", ".pptx", ".txt"}

    @classmethod
    def ensure_dirs(cls) -> None:
        """确保 MinerU staging 目录存在(本地 uploads/ 不再用于业务写入)。"""
        cls.MINERU_OUTDIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def validate(cls) -> None:
        """启动期校验:必填字段缺失立即失败(.env 缺关键字段时快速失败)。

        配合 _need() 实现 import-time 校验;这里再补一轮保险(部分可选字段也校验)。
        """
        # EMBEDDING_PROVIDER 必须是 bge-m3(其它供应商已废弃)
        if cls.EMBEDDING_PROVIDER != "bge-m3":
            raise RuntimeError(
                f"EMBEDDING_PROVIDER={cls.EMBEDDING_PROVIDER} 已被废弃。"
                f"企业版统一本地 BGE-M3,请设置 EMBEDDING_PROVIDER=bge-m3 并清空 Milvus 重建。"
            )
        # EMBEDDING_DIM 必须等于 1024(BGE-M3 固定)
        if cls.EMBEDDING_DIM != 1024:
            raise RuntimeError(
                f"EMBEDDING_DIM={cls.EMBEDDING_DIM} 与 BGE-M3(1024)不匹配。"
            )
        # WEB_SEARCH_ENABLED=True 时强制要求 BRAVE_SEARCH_API_KEY
        if cls.WEB_SEARCH_ENABLED and not cls.BRAVE_SEARCH_API_KEY:
            raise RuntimeError(
                "WEB_SEARCH_ENABLED=true 需要配置 BRAVE_SEARCH_API_KEY(.env)。"
            )
        # XHS_MCP_ENABLED=True 时强制要求 URL 非空(服务本体由用户独立部署,
        # 启动期不做网络探测 —— 只校验配置完整性,运行期失败走节点降级)
        if cls.XHS_MCP_ENABLED and not cls.XHS_MCP_URL.strip():
            raise RuntimeError(
                "XHS_MCP_ENABLED=true 需要配置 XHS_MCP_URL(.env,默认 http://127.0.0.1:18060/mcp)。"
            )

    @classmethod
    def llm_credentials(cls, role: str = "main") -> dict:
        """按 LLM_PROVIDER + role 返回对话模型的 (api_key, base_url, model)。"""
        if role not in ("main", "fast"):
            raise RuntimeError(f"未知的 LLM 角色: {role}(可选 main / fast)")
        if cls.LLM_PROVIDER == "minimax":
            return {
                "api_key": cls.MINIMAX_API_KEY,
                "base_url": cls.MINIMAX_BASE_URL,
                "model": cls.LLM_MODEL,
            }
        if cls.LLM_PROVIDER == "glm":
            if not cls.GLM_API_KEY:
                raise RuntimeError("LLM_PROVIDER=glm 需要配置 GLM_API_KEY。")
            return {
                "api_key": cls.GLM_API_KEY,
                "base_url": cls.GLM_BASE_URL,
                "model": cls.GLM_MODEL if role == "main" else cls.GLM_FAST_MODEL,
            }
        if cls.LLM_PROVIDER == "agnes":
            # agnes 只有单一 flash 文本档,main / fast 同模型
            if not cls.AGNES_API_KEY:
                raise RuntimeError("LLM_PROVIDER=agnes 需要配置 AGNES_API_KEY。")
            return {
                "api_key": cls.AGNES_API_KEY,
                "base_url": cls.AGNES_BASE_URL,
                "model": cls.AGNES_MODEL,
            }
        raise RuntimeError(f"不支持的 LLM_PROVIDER: {cls.LLM_PROVIDER}(可选 minimax / glm / agnes)")


# import-time 校验:缺关键字段即 RuntimeError,FastAPI 启动失败
Config.ensure_dirs()
Config.validate()
