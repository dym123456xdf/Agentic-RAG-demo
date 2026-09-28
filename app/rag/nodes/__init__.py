"""LangGraph 节点包 —— 入库图 7 节点 + 查询图 7 节点。

按 base.py 的 BaseNode 接口实现;flow 类属性区分 "ingest" 与 "query",
由基类 __call__ 决定日志前缀与异常类型。
"""
from app.rag.nodes.ingest_nodes import (
    NodeBgeEmbedding,
    NodeDocSplit,
    NodeEntry,
    NodeImportMilvus,
    NodeItemNameRecognition,
    NodeMdImg,
    NodePdfToMd,
)
from app.rag.nodes.query_nodes import (
    NodeCliffRerank,
    NodeEmbeddingSearch,
    NodeGenerate,
    NodeHydeSearch,
    NodePreprocess,
    NodeRrfFuse,
    NodeWebSearch,
)

__all__ = [
    # ingest
    "NodeEntry",
    "NodePdfToMd",
    "NodeMdImg",
    "NodeDocSplit",
    "NodeItemNameRecognition",
    "NodeBgeEmbedding",
    "NodeImportMilvus",
    # query
    "NodePreprocess",
    "NodeEmbeddingSearch",
    "NodeHydeSearch",
    "NodeWebSearch",
    "NodeRrfFuse",
    "NodeCliffRerank",
    "NodeGenerate",
]
