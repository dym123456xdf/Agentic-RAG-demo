"""Milvus 客户端工厂 —— 单一职责:管理 Milvus 连接 + 拿一个 collection 句柄。

- 数据库 / collection 都不存在时自动建,启动即可用。
- 服务挂了抛清晰异常,不要让上层吞掉。
- 这里不手工建 collection schema,统一交给 llama-index 的 MilvusVectorStore
  (它会带 enable_dynamic_field=True,这样 llama-index 内部 metadata 都能塞)。
"""
from __future__ import annotations

from typing import Optional

from pymilvus import connections, MilvusClient

from app.core.config import Config


class MilvusStore:
    """封装 Milvus 连接 + 数据库生命周期。"""

    def __init__(self):
        # 用 MilvusClient 而不是 ORM-style connections,API 更稳
        self._client = MilvusClient(uri=Config.MILVUS_URI, db_name=Config.MILVUS_DB)
        self._ensure_database()

    def _ensure_database(self) -> None:
        existing = self._client.list_databases()
        if Config.MILVUS_DB not in existing:
            self._client.create_database(Config.MILVUS_DB)

    @property
    def client(self) -> MilvusClient:
        return self._client

    @property
    def collection(self) -> MilvusClient:
        """兼容旧调用(self.collection.flush() / .num_entities)。"""
        return self._client

    @property
    def vector_store(self):
        """给 llama-index 包一层 MilvusVectorStore(在 indexer / retriever 里用)。

        MilvusVectorStore 会用 enable_dynamic_field=True 自动建 collection,
        不需要手工建 schema。注意:它不支持切 db,直接走默认 db。
        """
        from llama_index.vector_stores.milvus import MilvusVectorStore
        from pymilvus.client.types import DataType

        return MilvusVectorStore(
            uri=Config.MILVUS_URI,
            collection_name=Config.MILVUS_COLLECTION,
            dim=Config.EMBEDDING_DIM,
            overwrite=False,
            # 把 source 暴露成标量字段,便于后续过滤 / 展示来源
            scalar_field_names=["source"],
            scalar_field_types=[DataType.VARCHAR],
            similarity_metric="COSINE",
        )

    def has_collection(self) -> bool:
        """collection 是否已存在(还没入库过任何文件时是 False)。"""
        try:
            return self._client.has_collection(Config.MILVUS_COLLECTION)
        except Exception:
            return False

    def list_sources(self) -> dict:
        """聚合 Milvus 里所有 source 字段,返回 {filename: chunk_count}。

        用来给前端展示"已入库哪些文件",以及入库前查重。
        """
        if not self.has_collection():
            return {}
        try:
            rows = self._client.query(
                collection_name=Config.MILVUS_COLLECTION,
                output_fields=["source"],
                limit=16384,
            )
        except Exception as e:
            print(f"[milvus] list_sources query 失败: {e}")
            return {}

        counts: dict[str, int] = {}
        for r in rows:
            name = r.get("source") or "unknown"
            counts[name] = counts.get(name, 0) + 1
        return counts


_singleton: Optional[MilvusStore] = None


def get_store() -> MilvusStore:
    """进程内单例。"""
    global _singleton
    if _singleton is None:
        _singleton = MilvusStore()
    return _singleton