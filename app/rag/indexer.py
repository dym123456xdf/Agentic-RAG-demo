"""索引构建器 —— 单一职责:接收 Node 列表,跑 embedding + 写 Milvus + 返回可检索的索引对象。

两个动作封装在一个文件是因为它们都是"入库"这一个职能的两步:
1. VectorStoreIndex.from_nodes —— 触发 embed,塞进 Milvus。
2. 返回的 index 可以直接当 retriever 用。

幂等:
- 入库前先用 Milvus.list_sources() 拿已有 source 集合。
- 相同文件名的 Document 全部跳过,不入库、不消耗 embedding token。
- stats 里多返回 skipped_files / chunks_skipped。
"""
from __future__ import annotations

import hashlib

from llama_index.core import Document, Settings, StorageContext, VectorStoreIndex

from app.core.config import Config
from app.core.embedding import MiniMaxEmbedding
from app.core.milvus_client import get_store
from app.rag import loader, splitter


def _ensure_global_settings():
    """把 LLM/embedding 注册到 llama-index 全局 Settings,确保 index 知道怎么向量化。"""
    Settings.embed_model = MiniMaxEmbedding()


def _doc_id_for(node) -> str:
    """给每个 node 一个稳定 doc_id,用于检索阶段定位来源文件。"""
    src = node.metadata.get("source", "unknown")
    txt = node.get_content()[:50]
    return hashlib.md5(f"{src}|{txt}".encode()).hexdigest()[:16]


def build_from_path(path: str) -> dict:
    """一站式:文件/目录 → 索引已写入 Milvus → 返回入库统计。

    幂等行为:同名文件已在库中就直接跳过,不会重复写 chunk、不会重复调 embedding。
    """
    _ensure_global_settings()
    store = get_store()

    docs = loader.load(path)

    # 查重:按文件名(source 字段)过滤已存在的文档
    existing = store.list_sources()  # {filename: chunk_count}
    new_docs = []
    skipped_files: list[str] = []
    for d in docs:
        src = d.metadata.get("source", "")
        if src in existing:
            skipped_files.append(src)
        else:
            new_docs.append(d)

    if not new_docs:
        # 全部重复,直接返回
        return {
            "files": 0,
            "chunks_ingested": 0,
            "skipped_files": skipped_files,
            "chunks_skipped": sum(existing.get(s, 0) for s in skipped_files),
            "total_entities": store.collection.get_collection_stats(
                Config.MILVUS_COLLECTION
            ).get("row_count", 0) if store.has_collection() else 0,
        }

    # 切分 + 入库 —— 只对未入库的文件做
    nodes = splitter.split(new_docs)

    # sanitize:只保留 source / doc_id 两个 metadata 字段
    # MarkdownNodeParser 会塞 header_path / header 等额外键,Milvus 不允许未注册字段
    for n in nodes:
        n.metadata = {
            "source": n.metadata.get("source", "unknown"),
        }
        n.metadata["doc_id"] = _doc_id_for(n)

    storage_ctx = StorageContext.from_defaults(vector_store=store.vector_store)
    VectorStoreIndex.from_documents(
        [Document(text=n.get_content(), metadata=n.metadata) for n in nodes],
        storage_context=storage_ctx,
        show_progress=True,
        transformations=[],   # 已在 splitter 里切过,不再二次切
    )

    # 落库触发
    store.collection.flush(Config.MILVUS_COLLECTION)
    stats = store.collection.get_collection_stats(Config.MILVUS_COLLECTION)
    count = stats.get("row_count", 0)
    return {
        "files": len(new_docs),
        "chunks_ingested": len(nodes),
        "skipped_files": skipped_files,
        "chunks_skipped": sum(existing.get(s, 0) for s in skipped_files),
        "total_entities": count,
    }


def load_existing_index() -> VectorStoreIndex:
    """从已有 Milvus collection 拿可检索的 index 对象(不重新 embedding)。"""
    _ensure_global_settings()
    store = get_store()
    storage_ctx = StorageContext.from_defaults(vector_store=store.vector_store)
    return VectorStoreIndex.from_vector_store(
        vector_store=store.vector_store,
        storage_context=storage_ctx,
    )
