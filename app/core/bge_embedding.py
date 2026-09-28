"""BGE-M3 本地嵌入 —— 单一职责:用 FlagEmbedding 加载 BAAI/bge-m3,产出 dense(1024)+sparse 双向量。

为什么不用云端 embedding:
- 速度:本地推理(MPS / CUDA)延迟 < 50ms,云端往返 200-500ms;
- 成本:无 API 费用;
- 稀疏优势:BGE-M3 是当前少有的 learned sparse(非 BM25)开源模型,与 dense 同源,语义对齐。

为什么单 provider:
- 配置侧 EMBEDDING_PROVIDER 只剩 bge-m3 一档(旧 embo-01 / embedding-3 已在 config.py 校验里拒绝);
- 切 provider 必清库重建 —— 与 CLAUDE.md 硬约束一致。

输出维度:dense 固定 1024 维(COSINE 距离越小越相关,见 milvus_hybrid 头注释);
稀疏向量是 BGE-M3 lexical weights(CSR 字典:{token_id: weight})。
"""
from __future__ import annotations

import threading
from typing import Any

from llama_index.core.embeddings import BaseEmbedding

from app.core.config import Config


_model: Any = None  # FlagEmbedding.BGEM3FlagModel 单例,延迟加载
_model_lock = threading.Lock()


def _get_model():
    """进程内单例:BGEM3FlagModel 冷启 ~3-5s,只加载一次。

    ⚠️ 必须持锁双检:查询图 embedding_search / hyde_search 两节点并行执行,
    无锁时两个线程同时看到 _model is None,各自加载一份模型(MPS 上双重权重
    转换极慢 + 显存翻倍,实测卡死),第二个加载结果还会覆盖第一个。
    """
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from FlagEmbedding import BGEM3FlagModel
                import torch

                device = Config.BGE_M3_DEVICE
                if device == "mps" and not torch.backends.mps.is_available():
                    print("[bge_embedding] MPS 不可用,fallback 到 CPU")
                    device = "cpu"
                use_fp16 = device != "cpu"
                _model = BGEM3FlagModel(
                    Config.BGE_M3_MODEL,
                    use_fp16=use_fp16,
                    device=device,
                )
    return _model


# ⚠️ 推理同样必须持锁:torch MPS 后端不支持多线程并发跑同一模型(实测并发
# encode 直接 Segmentation fault),查询图两路召回并行线程靠这把锁串行化。
# BGE-M3 单条 encode 毫秒级,串行化对延迟无感知。


def _csr_to_dict(csr) -> dict[int, float]:
    """scipy CSR / BGE-M3 输出的 sparse 行向量 → {token_id: weight} 字典。

    BGE-M3 输出的 sparse 是 scipy.sparse.csr_matrix,取第 0 行后转 dict;
    非空索引作为 token id(模型 vocab 内整数索引),值作为权重。
    """
    if csr is None:
        return {}
    # csr 可能是单行(1, vocab_size)或数组;统一取第 0 行
    row = csr[0] if hasattr(csr, "__getitem__") and hasattr(csr, "shape") else csr
    try:
        # scipy.sparse 行向量
        coo = row.tocoo()
        return {int(col): float(val) for col, val in zip(coo.col, coo.data, strict=False)}
    except AttributeError:
        # 兜底:当作普通 dict / 可迭代
        try:
            return {int(k): float(v) for k, v in dict(row).items()}
        except Exception:
            return {}


def _encode_dense(texts: list[str]) -> list[list[float]]:
    """dense 向量批量编码,返回 List[List[float]],每条长度 1024。"""
    model = _get_model()  # 先确保加载(加载自身已持锁;不要放进下面的 with,非重入锁会自死锁)
    with _model_lock:
        out = model.encode(
            texts,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
    return [vec.tolist() for vec in out["dense_vecs"]]


def _encode_sparse(texts: list[str]) -> list[dict[int, float]]:
    """稀疏向量批量编码,返回 List[Dict[int, float]],每条 CSR 字典。"""
    model = _get_model()
    with _model_lock:
        out = model.encode(
            texts,
            return_dense=False,
            return_sparse=True,
            return_colbert_vecs=False,
        )
    return [_csr_to_dict(lex) for lex in out["lexical_weights"]]


class BGEEmbedding(BaseEmbedding):
    """llama-index 适配的 BGE-M3 嵌入,BaseEmbedding 接口只暴露 dense。"""

    def __init__(self, model_name: str | None = None, embed_batch_size: int = 8):
        super().__init__(
            model_name=model_name or Config.BGE_M3_MODEL,
            embed_batch_size=embed_batch_size,
        )

    # ============== BaseEmbedding 必须实现的钩子(仅返回 dense) ==============
    def _get_query_embedding(self, query: str) -> list[float]:
        return _encode_dense([query])[0]

    def _get_text_embedding(self, text: str) -> list[float]:
        return _encode_dense([text])[0]

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return _encode_dense(texts)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return self._get_text_embedding(text)

    async def _aget_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return self._get_text_embeddings(texts)


def encode_sparse(text: str) -> dict[int, float]:
    """单条文本稀疏向量 —— Milvus hybrid_search 直接使用。"""
    return _encode_sparse([text])[0]


def encode_sparse_batch(texts: list[str]) -> list[dict[int, float]]:
    """批量稀疏向量 —— 入库节点使用。"""
    return _encode_sparse(texts)


def get_bge_embedding() -> BGEEmbedding:
    """入库 / 索引构建用的 dense 入口。"""
    return BGEEmbedding()
