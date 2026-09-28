"""入库 StateGraph 装配 —— 7 节点线性,entry → ... → import_milvus → END。

入口 ingest() 在 pipeline.py;本模块只负责图编译,产物 INGEST_GRAPH 是单例。
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.rag.nodes import (
    NodeBgeEmbedding,
    NodeDocSplit,
    NodeEntry,
    NodeImportMilvus,
    NodeItemNameRecognition,
    NodeMdImg,
    NodePdfToMd,
)
from app.rag.state import ImportGraphState

_builder = StateGraph(ImportGraphState)
_builder.add_node("entry", NodeEntry())
_builder.add_node("pdf_to_md", NodePdfToMd())
_builder.add_node("md_img", NodeMdImg())
_builder.add_node("doc_split", NodeDocSplit())
_builder.add_node("item_name_recognition", NodeItemNameRecognition())
_builder.add_node("bge_embedding", NodeBgeEmbedding())
_builder.add_node("import_milvus", NodeImportMilvus())

_builder.set_entry_point("entry")
_builder.add_edge("entry", "pdf_to_md")
_builder.add_edge("pdf_to_md", "md_img")
_builder.add_edge("md_img", "doc_split")
_builder.add_edge("doc_split", "item_name_recognition")
_builder.add_edge("item_name_recognition", "bge_embedding")
_builder.add_edge("bge_embedding", "import_milvus")
_builder.add_edge("import_milvus", END)

INGEST_GRAPH = _builder.compile()
