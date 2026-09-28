"""LangGraph 状态契约 —— 单一职责:入库图 / 查询图的 TypedDict 状态字段定义。

为什么 TypedDict + total=False:
- LangGraph 节点拿到的是 dict(可缺失键),不强制类型;声明成 TypedDict 让 IDE 提示可用字段;
- total=False 让所有字段都是可选的,节点间增量写入,缺失视为空值(节点内部兜底)。

为什么用 deep copy 工厂:
- LangGraph 复用同一份默认状态会导致跨请求污染;create_default_* 每次返回独立副本。
"""
from __future__ import annotations

import copy
from typing import TypedDict


# ===================== 入库图状态 =====================

class ImportGraphState(TypedDict, total=False):
    # 任务追踪
    task_id: str
    # 路径(均为 MinIO 对象 key)
    import_file_path: str  # uploads/<name>
    pdf_path: str          # uploads/<name>(MinerU 转换前的源文件)
    md_path: str           # converted/<stem>/<stem>.md
    file_dir: str          # converted/<stem>/(MinIO 前缀)
    # 文件元数据
    file_title: str        # 原文件名去后缀
    item_name: str         # 商品/主题名(可选)
    # 中间数据
    md_content: str        # MinerU 转换后的 md 文本(已抽取 base64 图)
    chunks: list[dict]     # 切分结果,每条 {text, metadata, doc_id, dense, sparse}
    # 控制标志
    is_pdf_read_enabled: bool   # 本期关闭
    is_md_read_enabled: bool    # 本期开启
    # ⚠️ 写入结果指标 —— 必须在 TypedDict 声明,否则 LangGraph 不会跟踪这个 channel,
    # 节点写入的值会被丢弃,导致 ainvoke 最终 state 取不到。
    chunks_ingested: int        # 实际写入 Milvus 的条数
    uploaded_objects: int       # 成功上传到 MinIO 的对象数


_IMPORT_DEFAULT: ImportGraphState = {
    "task_id": "",
    "is_pdf_read_enabled": False,
    "is_md_read_enabled": True,
    "import_file_path": "",
    "pdf_path": "",
    "md_path": "",
    "file_dir": "",
    "file_title": "",
    "item_name": "",
    "md_content": "",
    "chunks": [],
    "chunks_ingested": 0,
    "uploaded_objects": 0,
}


def create_default_import_state(**overrides) -> ImportGraphState:
    """创建入库图默认状态,支持覆盖字段。"""
    state = copy.deepcopy(_IMPORT_DEFAULT)
    state.update(overrides)
    return state


# ===================== 查询图状态 =====================

class QueryGraphState(TypedDict, total=False):
    # 标识
    session_id: str | int
    message_id: str | int
    # 原始 / 改写 / 意图
    original_query: str
    rewritten_query: str
    intent: str  # factual / explanatory / comparison / creative / chitchat
    # 商品 / 主题上下文(可选)
    item_name: str
    # 多路召回结果
    embedding_chunks: list[dict]        # 向量召回
    hyde_embedding_chunks: list[dict]   # HyDE 召回
    web_search_docs: list[dict]         # Web 召回
    # 融合 + 重排
    rrf_chunks: list[dict]
    reranked_docs: list[dict]
    # 提示词与生成
    prompt: str
    answer: str
    # 上下文
    history: list[dict]                 # 从 MySQL 注入
    is_stream: bool


_QUERY_DEFAULT: QueryGraphState = {
    "session_id": 0,
    "message_id": 0,
    "original_query": "",
    "rewritten_query": "",
    "intent": "factual",
    "item_name": "",
    "embedding_chunks": [],
    "hyde_embedding_chunks": [],
    "web_search_docs": [],
    "rrf_chunks": [],
    "reranked_docs": [],
    "prompt": "",
    "answer": "",
    "history": [],
    "is_stream": False,
}


def create_default_query_state(**overrides) -> QueryGraphState:
    """创建查询图默认状态,支持覆盖字段。"""
    state = copy.deepcopy(_QUERY_DEFAULT)
    state.update(overrides)
    return state
