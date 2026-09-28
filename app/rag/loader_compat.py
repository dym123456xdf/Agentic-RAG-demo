"""loader 兼容垫片 —— 旧 app/rag/loader.py 已废弃,这里保留白名单常量
供 upload.py 的 _has_converted / get_converted 沿用,不依赖具体 loader 函数。
"""
from __future__ import annotations

# 原 loader.py:MINERU_CONVERTIBLE
MINERU_CONVERTIBLE = {".pdf", ".docx", ".pptx"}
