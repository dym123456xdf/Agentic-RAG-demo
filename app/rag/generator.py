"""答案生成器 —— 单一职责:把重排后的节点拼成上下文,调 LLM 出答案 + 来源。

输出 schema:
{
  "answer": str,
  "sources": [
     {"index": 1, "content": "片段预览...", "score": 1.23, "confidence": 0.83, "source": "文件名"},
     ...
  ]
}
- score 是重排模型原始 logit(约 -10~10);confidence 是 sigmoid(score) 的 0-1 置信度。
- 流式出口 generate_stream():先出 sources(meta 事件用),再逐块 yield 清洗后答案文本。
"""
from __future__ import annotations

import re
from typing import Iterator

from llama_index.core.schema import NodeWithScore

from app.core.llm import LLMClient, ThinkStreamFilter

SYSTEM = (
    "你是一个严谨的个人知识库助手。回答用户问题时,只能依据下方提供的【参考资料】;"
    '如果资料里没有答案,就明确说"我不知道,资料里没提到",不要编造。'
    "回答完简要回答后,用一句话给出最相关的 1-3 条来源编号。"
    "参考资料中的图片引用(形如 ![...](/converted/...) 的 markdown 语法)必须逐字原样保留进答案,"
    "不得改写、缩写或编造任何图片路径;参考资料里没有图片引用时,答案里不得出现任何图片语法。"
)

# 片段全文里的 markdown 图片引用,用于截断后完整回填(防长引用被 200 字符截在中间)
_IMG_REF_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")


def build_sources(nodes: list[NodeWithScore]) -> list[dict]:
    """sources 构建(非流式与流式共用):逐条带 0-1 confidence(post 未跑过时为 None)。"""
    return [
        {
            "index": i,
            "content": n.node.get_content().strip()[:300],
            "score": round(float(n.score or 0.0), 4),
            "confidence": getattr(n, "confidence", None),
            "source": n.node.metadata.get("source", "unknown"),
        }
        for i, n in enumerate(nodes, 1)
    ]


class Generator:
    def __init__(self):
        # 生成质量优先,走 main 档(与预处理 fast 档分层)
        self._llm = LLMClient(role="main")

    @staticmethod
    def _build_context(query: str, nodes: list[NodeWithScore]) -> str:
        """拼参考资料 + 用户消息(非流式/流式共用)。"""
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
        return (
            f"用户问题: {query}\n\n"
            f"【参考资料】\n{context}\n\n"
            "请基于上面的资料给出回答。"
        )

    def _messages(self, query: str, nodes: list[NodeWithScore]) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": self._build_context(query, nodes)},
        ]

    def generate(self, query: str, nodes: list[NodeWithScore]) -> dict:
        if not nodes:
            return {
                "answer": "我不知道,资料里没提到。",
                "sources": [],
            }
        messages = self._messages(query, nodes)
        answer = self._llm.chat(messages, temperature=0.2, max_tokens=800)
        return {"answer": answer, "sources": build_sources(nodes)}

    def generate_stream(self, query: str, nodes: list[NodeWithScore]) -> tuple[Iterator[str], list[dict]]:
        """generate 的流式版:返回 (逐块文本迭代器, sources)。

        - sources 在流开始前就构建好(路由用它先发 meta 事件,前端先渲染来源块);
        - 迭代器逐块 yield **已清洗**(ThinkStreamFilter 剥 think)的答案增量;
        - 空 nodes 时不调 LLM,直接出"我不知道"一条,行为与非流式一致。
        """
        sources = build_sources(nodes)
        if not nodes:
            return iter(["我不知道,资料里没提到。"]), sources

        def _stream() -> Iterator[str]:
            filt = ThinkStreamFilter()
            messages = self._messages(query, nodes)
            for delta in self._llm.stream_chat(messages, temperature=0.2, max_tokens=800):
                out = filt.push(delta)
                if out:
                    yield out
            tail = filt.flush()
            if tail:
                yield tail

        return _stream(), sources
