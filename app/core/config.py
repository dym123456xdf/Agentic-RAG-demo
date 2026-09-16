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
    # provider 切换:minimax(默认)/ glm(智谱 / Z.ai),两者都是 OpenAI 兼容协议
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "minimax").strip().lower()
    MINIMAX_API_KEY: str = _need("MINIMAX_API_KEY")
    MINIMAX_BASE_URL: str = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "MiniMax-M3")

    # ====== GLM(智谱开放平台 / Z.ai,仅 LLM_PROVIDER=glm 时必填)======
    GLM_API_KEY: str = os.getenv("GLM_API_KEY", "")
    GLM_BASE_URL: str = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    # glm-5.3-flash:旗舰同代、1M 上下文、0.8/2.8 元每百万 token;免费档可用 glm-4.7-flash
    GLM_MODEL: str = os.getenv("GLM_MODEL", "glm-5.3-flash")
    # fast 档(免费):意图识别 / 改写 / 扩展等预处理短输出任务
    GLM_FAST_MODEL: str = os.getenv("GLM_FAST_MODEL", "glm-4.7-flash")

    # ====== Embedding(向量入库 + 查询)======
    # provider:minimax(embo-01,私有协议,1536 维)/ glm(Embedding-3,OpenAI 兼容,默认 1024 维)
    # 注意:切换 provider = 更换向量空间,必须清空 Milvus collection 重建!
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "minimax").strip().lower()
    # embo-01 必填 GroupId(MiniMax 强制,丢在 URL query,不传 400)
    MINIMAX_GROUP_ID: str = _need("MINIMAX_GROUP_ID")
    _glm_emb = EMBEDDING_PROVIDER == "glm"
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "embedding-3" if _glm_emb else "embo-01")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "1024" if _glm_emb else "1536"))

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

    @classmethod
    def llm_credentials(cls, role: str = "main") -> dict:
        """按 LLM_PROVIDER + role 返回对话模型的 (api_key, base_url, model)。

        role:main(答案生成,质量优先)/ fast(意图 / 改写 / 扩展等预处理,成本优先)。
        glm 双档位:main=GLM_MODEL,fast=GLM_FAST_MODEL(默认免费档 glm-4.7-flash);
        minimax 无免费档,两档同模型。
        延续快速失败哲学:provider / role 非法或缺 key 时启动即报错,不拖到运行时。
        """
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
                raise RuntimeError(
                    "LLM_PROVIDER=glm 需要配置 GLM_API_KEY(智谱开放平台或 Z.ai 的 API Key,"
                    "见项目根 .env)。"
                )
            return {
                "api_key": cls.GLM_API_KEY,
                "base_url": cls.GLM_BASE_URL,
                "model": cls.GLM_MODEL if role == "main" else cls.GLM_FAST_MODEL,
            }
        raise RuntimeError(f"不支持的 LLM_PROVIDER: {cls.LLM_PROVIDER}(可选 minimax / glm)")


Config.ensure_dirs()
