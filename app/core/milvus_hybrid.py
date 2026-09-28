"""Milvus 混合检索客户端 —— 单一职责:管理 hybrid(dense + sparse)collection 与 hybrid_search()。

⚠️ 分数语义(两套,别混淆):
   - 单路向量 search(dense COSINE):返回的是「距离」,越小越相关 —— 与相似度语义相反;
   - 本模块的 hybrid_search(WeightedRanker 融合):返回的 "distance" 字段是归一化后的
     融合**相似度**,越大越相关(实测验证:最相关 hit 的值最大)。
   本模块已把后者直接暴露为 score(越大越相关),下游节点按 score 降序即可,不要再取负。

Schema 设计:
  - dense:    FLOAT_VECTOR(1024)  HNSW, COSINE
  - sparse:   SPARSE_FLOAT_VECTOR  SPARSE_INVERTED_INDEX, IP(Inner Product,越大越相关)
  - text:     VARCHAR(4096)  文本片段
  - doc_name: VARCHAR(256)   原文件名(删除/去重 key)
  - file_dir: VARCHAR(512)   MinIO 前缀(converted/<stem>/)
  - chunk_idx:INT64          chunk 在原文档中的顺序
  - metadata: JSON(dynamic)  其他元数据

库内加权融合:WeightedRanker(0.8, 0.2) → dense 主导、sparse 辅助。
"""
from __future__ import annotations

import logging
from typing import Any

from pymilvus import (
    AnnSearchRequest,
    CollectionSchema,
    DataType,
    FieldSchema,
    MilvusClient,
    WeightedRanker,
)
# pymilvus 2.6.x:IndexParams 不暴露在顶层,要从子模块导入
from pymilvus.milvus_client.index import IndexParams

from app.core.config import Config

logger = logging.getLogger("milvus_hybrid")

_client: MilvusClient | None = None


def _make_client() -> MilvusClient:
    return MilvusClient(uri=Config.MILVUS_URI, db_name=Config.MILVUS_DB)


def get_client() -> MilvusClient:
    global _client
    if _client is None:
        _client = _make_client()
    return _client


def _ensure_database() -> None:
    """确保 MILVUS_DB 存在;用默认 db 上下文创建新 db(pymilvus 限制)。

    pymilvus MilvusClient 绑定到非默认 db 后,create_database 会失败/静默;
    必须先创建一个 default-bound 客户端来建库,然后主客户端才能用。
    """
    target = Config.MILVUS_DB
    if target == "default":
        return  # 永远存在
    client = get_client()
    if target in client.list_databases():
        return
    # 用 default 上下文建库
    bootstrap = MilvusClient(uri=Config.MILVUS_URI, db_name="default")
    if target not in bootstrap.list_databases():
        bootstrap.create_database(target)
        logger.info(f"创建 Milvus 数据库: {target}")


def has_collection() -> bool:
    try:
        return bool(get_client().has_collection(Config.MILVUS_COLLECTION))
    except Exception:
        return False


def _ensure_indexes(name: str) -> None:
    """索引自愈:schema 正确但 dense/sparse 索引缺失时补建并 load。

    背景:Milvus streaming node 模式下新建 collection 不会自动建向量索引;历史环境也
    出现过"schema 对、dense 索引丢失"导致 load/search 报错(需 /upload/clear 救回)的
    情况。此处启动时统一兜底,索引齐了只做幂等 load。
    """
    client = get_client()
    try:
        existing = set(client.list_indexes(collection_name=name))
    except Exception:
        existing = set()
    missing = [f for f in ("dense", "sparse") if f not in existing]
    if missing:
        # pymilvus 2.6.x:create_index 要求 IndexParams 对象,不是 dict。
        ip_params = IndexParams()
        if "dense" in missing:
            ip_params.add_index(
                field_name="dense",
                index_type="HNSW",
                metric_type="COSINE",
                params={"M": 16, "efConstruction": 64},
            )
        if "sparse" in missing:
            ip_params.add_index(
                field_name="sparse",
                index_type="SPARSE_INVERTED_INDEX",
                metric_type="IP",
                params={"drop_ratio_build": 0.1},
            )
        client.create_index(collection_name=name, index_params=ip_params)
        logger.info(f"补建索引({','.join(missing)}): {name}")
    # 加载 collection 进内存(Woodpecker MQ streaming node 必须显式 load,
    # 否则 search/query 会报 "collection not loaded")。
    client.load_collection(name)


def ensure_collection(dim: int = 1024) -> None:
    """启动钩子:collection 不存在则建,旧 schema(无 sparse 字段)按 AUTO_REBUILD_SCHEMA 处理。

    自动建 schema:
      - 字段:id(INT64 PK auto)/ text(VARCHAR 4096)/ dense(FLOAT_VECTOR 1024)/
        sparse(SPARSE_FLOAT_VECTOR)/ doc_name(VARCHAR 256)/ file_dir(VARCHAR 512)/
        chunk_idx(INT64)/ metadata(JSON, enable_dynamic=True)
      - 索引:dense HNSW(COSINE)/ sparse SPARSE_INVERTED_INDEX(IP)
    """
    _ensure_database()
    client = get_client()
    name = Config.MILVUS_COLLECTION

    if not client.has_collection(name):
        # pymilvus 2.6.x MilvusClient.create_collection 的 kwargs 兼容性差
        # (PrimaryKeyException:primary_field must be int or str),用 schema 显式构造更稳。
        schema = CollectionSchema(
            fields=[
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=4096),
                FieldSchema(name="dense", dtype=DataType.FLOAT_VECTOR, dim=dim),
                FieldSchema(name="sparse", dtype=DataType.SPARSE_FLOAT_VECTOR),
                FieldSchema(name="doc_name", dtype=DataType.VARCHAR, max_length=256),
                FieldSchema(name="file_dir", dtype=DataType.VARCHAR, max_length=512),
                FieldSchema(name="chunk_idx", dtype=DataType.INT64),
                FieldSchema(name="metadata", dtype=DataType.JSON),
            ],
            description="hybrid rag chunks",
            enable_dynamic_field=True,
        )
        client.create_collection(
            collection_name=name,
            schema=schema,
        )
        # 索引 + load 统一走自愈(streaming node 下新建 collection 不自动建向量索引)
        _ensure_indexes(name)
        logger.info(f"创建 hybrid collection: {name}")
        return

    # 已存在:检测是否为 hybrid schema(sparse 字段是否在)
    try:
        schema = client.describe_collection(name)
        field_names = {f["name"] for f in schema.get("fields", [])}
    except Exception:
        field_names = set()
    if "sparse" in field_names:
        _ensure_indexes(name)  # schema 对但索引可能缺失(streaming node 历史坑),自愈补建
        return  # 已经是 hybrid,不动

    # 旧 schema(无 sparse)处理
    if Config.AUTO_REBUILD_SCHEMA:
        logger.warning(
            f"检测到旧 schema(缺 sparse 字段),按 AUTO_REBUILD_SCHEMA=true drop 重建: {name}"
        )
        client.drop_collection(name)
        ensure_collection(dim)
    else:
        raise RuntimeError(
            f"collection {name} 是旧 schema(无 sparse 字段)。"
            f"请设置 AUTO_REBUILD_SCHEMA=true 自动重建,或手动 drop_collection 后重启。"
        )


def insert_chunks(chunks: list[dict]) -> int:
    """批量写入 chunks,跳过 dense/sparse 任一为空的;返回实际写入数。"""
    if not chunks:
        return 0
    client = get_client()
    rows: list[dict[str, Any]] = []
    skipped = 0
    for c in chunks:
        dense = c.get("dense")
        sparse = c.get("sparse")
        if not dense or not sparse:
            skipped += 1
            logger.info(f"skip chunk idx={c.get('chunk_idx')} due to empty vector")
            continue
        rows.append({
            "text": c["text"][:4096],
            "dense": dense,
            "sparse": sparse,
            "doc_name": c.get("doc_name", "")[:256],
            "file_dir": c.get("file_dir", "")[:512],
            "chunk_idx": int(c.get("chunk_idx", 0)),
            "metadata": c.get("metadata", {}),
        })
    if not rows:
        return 0
    client.insert(collection_name=Config.MILVUS_COLLECTION, data=rows)
    client.flush(Config.MILVUS_COLLECTION)
    if skipped:
        logger.info(f"insert_chunks: 写入 {len(rows)} 条,跳过 {skipped} 条空向量")
    return len(rows)


def hybrid_search(dense_vec: list[float], sparse_vec: dict[int, float],
                  top_k: int = 20, filter_expr: str | None = None) -> list[dict]:
    """dense + sparse 加权融合检索;返回 [{text, doc_name, file_dir, chunk_idx, metadata, score}]。

    score 语义:WeightedRanker 输出的融合相似度,越大越相关(见模块头注释),结果按
    score 降序使用即可,不要再做 1-x / 取负等反转。
    """
    client = get_client()
    # 防止 cold collection(Milvus streaming node 不会自动 load)
    try:
        load_state = client.get_load_state(collection_name=Config.MILVUS_COLLECTION)
        if load_state.get("state") != 3:  # LoadState.Loaded
            client.load_collection(Config.MILVUS_COLLECTION)
    except Exception:
        client.load_collection(Config.MILVUS_COLLECTION)
    dense_req = AnnSearchRequest(
        data=[dense_vec],
        anns_field="dense",
        param={"metric_type": "COSINE", "params": {"ef": 128}},
        limit=top_k,
        expr=filter_expr,
    )
    sparse_req = AnnSearchRequest(
        data=[sparse_vec],
        anns_field="sparse",
        param={"metric_type": "IP", "params": {}},
        limit=top_k,
        expr=filter_expr,
    )
    ranker = WeightedRanker(0.8, 0.2)  # dense 0.8 / sparse 0.2
    results = client.hybrid_search(
        collection_name=Config.MILVUS_COLLECTION,
        reqs=[dense_req, sparse_req],
        ranker=ranker,
        limit=top_k,
        output_fields=["text", "doc_name", "file_dir", "chunk_idx", "metadata"],
    )
    out: list[dict] = []
    for hits in results:
        for h in hits:
            out.append({
                "id": h.get("id"),
                "text": h.get("text", ""),
                "doc_name": h.get("doc_name", ""),
                "file_dir": h.get("file_dir", ""),
                "chunk_idx": h.get("chunk_idx", 0),
                "metadata": h.get("metadata", {}) or {},
                # WeightedRanker 的输出是「越大越相似」的融合相似度(实测:最相关 hit 的
                # distance 值最大),直接作为 score 使用 —— 不要按"距离"语义取负!
                "distance": h.get("distance", 0.0),
                "score": float(h.get("distance", 0.0)),
            })
    return out


def delete_by_doc_name(name: str) -> int:
    """按 doc_name 删除全部 chunk,返回删除条数;collection 不存在返回 0。"""
    if not has_collection():
        return 0
    client = get_client()
    escaped = name.replace('"', '\\"')
    result = client.delete(
        collection_name=Config.MILVUS_COLLECTION,
        filter=f'doc_name == "{escaped}"',
    )
    return int(result.get("delete_count", 0) or 0)


def list_doc_names() -> dict[str, int]:
    """返回 {filename: chunk_count};collection 不存在返回 {}。"""
    if not has_collection():
        return {}
    client = get_client()
    # collection 必须在 load 状态才能 query
    try:
        client.load_collection(Config.MILVUS_COLLECTION)
    except Exception:
        pass
    try:
        rows = client.query(
            collection_name=Config.MILVUS_COLLECTION,
            output_fields=["doc_name"],
            limit=16384,
            # 默认 Bounded 级别下 delete 后有秒级延迟才可见,前端"删除→刷新列表"会看到
            # 幽灵文件;Strong 读最新已提交数据(实测立即生效,列表场景数据量小无感)
            consistency_level="Strong",
        )
    except Exception as e:
        logger.warning(f"list_doc_names query 失败: {e}")
        return {}
    counts: dict[str, int] = {}
    for r in rows:
        n = r.get("doc_name") or "unknown"
        counts[n] = counts.get(n, 0) + 1
    return counts


def drop_collection() -> None:
    """彻底删除 collection(谨慎;POST /upload/clear 用)。"""
    client = get_client()
    if client.has_collection(Config.MILVUS_COLLECTION):
        client.drop_collection(Config.MILVUS_COLLECTION)
