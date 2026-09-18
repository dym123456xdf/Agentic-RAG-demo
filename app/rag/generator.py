"""答案生成器 —— 单一职责:把重排后的节点拼成上下文,调 LLM 出答案 + 来源。

输出 schema:
{
  "answer": str,
  "sources": [
     {"index": 1, "content": "片段预览...", "score": 0.95, "source": "文件名"},
     ...
  ]
}
"""
from __future__ import annotations

import re

from llama_index.core.schema import NodeWithScore

from app.core.llm import LLMClient

SYSTEM = (
    "你是一个严谨的个人知识库助手。回答用户问题时,只能依据下方提供的【参考资料】;"
    '如果资料里没有答案,就明确说"我不知道,资料里没提到",不要编造。'
    "回答完简要回答后,用一句话给出最相关的 1-3 条来源编号。"
    "参考资料中的图片引用(形如 ![...](/converted/...) 的 markdown 语法)必须逐字原样保留进答案,"
    "不得改写、缩写或编造任何图片路径;参考资料里没有图片引用时,答案里不得出现任何图片语法。"
)

# 片段全文里的 markdown 图片引用,用于截断后完整回填(防长引用被 200 字符截在中间)
_IMG_REF_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")


class Generator:
    def __init__(self):
        # 生成质量优先,走 main 档(与预处理 fast 档分层)
        self._llm = LLMClient(role="main")

    def generate(self, query: str, nodes: list[NodeWithScore]) -> dict:
        if not nodes:
            return {
                "answer": "我不知道,资料里没提到。",
                "sources": [],
            }

        context_blocks = []
        for i, n in enumerate(nodes, 1):
            source = n.node.metadata.get("source", "unknown")
            doc_id = n.node.metadata.get("doc_id", "")
            content = n.node.get_content().strip()
            snippet = content.replace("\n", " ")[:200]
            # 图片引用整条抽出、截断后完整追加:LLM 拿到半截 URL 会脑补路径
            img_refs = list(dict.fromkeys(_IMG_REF_RE.findall(content)))
            if img_refs:
                snippet += "\n[本片段完整图片引用,回答时原样保留: " + " ".join(img_refs) + "]"
            context_blocks.append(
                f"[{i}] (来源:{source} | doc_id={doc_id} | 相关度:{n.score:.3f})\n{snippet}..."
            )
        context = "\n\n".join(context_blocks)

        user_msg = (
            f"用户问题: {query}\n\n"
            f"【参考资料】\n{context}\n\n"
            "请基于上面的资料给出回答。"
        )

        answer = self._llm.chat(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_msg}],
            temperature=0.2,
            max_tokens=800,
        )

        sources = [
            {
                "index": i,
                "content": n.node.get_content().strip()[:300],
                "score": round(float(n.score or 0.0), 4),
                "source": n.node.metadata.get("source", "unknown"),
            }
            for i, n in enumerate(nodes, 1)
        ]

        return {"answer": answer, "sources": sources}
