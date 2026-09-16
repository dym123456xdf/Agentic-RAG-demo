"""查询预处理器 —— 单一职责:把用户的原始问题加工成"更适合检索"的结构化查询。

内部三步:
1. 意图识别(factual / explanatory / comparison / creative / chitchat) —— 留口子给后续差异化
2. 多轮改写 —— 结合对话历史补全指代
3. 查询扩展 —— 生成 N 个语义相关问题,扩大召回覆盖面

三步属于同一职能(预处理),不拆三个文件;但彼此独立、可关。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.llm import LLMClient

INTENT_LABELS = ["factual", "explanatory", "comparison", "creative", "chitchat"]
HISTORY_WINDOW = 3  # 最近 3 轮足够覆盖上下文指代


@dataclass
class ProcessedQuery:
    original: str
    rewritten: str
    expanded: list[str] = field(default_factory=list)
    intent: str = "factual"


class QueryPreProcessor:
    """调用一次 LLM 不划算,所以一次 prompt 把三件事都问完。"""

    def __init__(self, llm: LLMClient | None = None):
        # 预处理(意图 / 改写 / 扩展)都是短输出轻量任务,走 fast 免费档
        self._llm = llm or LLMClient(role="fast")

    def process(self, query: str, history: list[dict[str, str]] | None = None) -> ProcessedQuery:
        history = history or []
        recent = history[-HISTORY_WINDOW * 2:]  # user+assistant 算一对

        rewritten = self._rewrite(query, recent)
        intent = self._intent(rewritten)
        expanded = self._expand(rewritten)

        return ProcessedQuery(
            original=query,
            rewritten=rewritten,
            expanded=expanded,
            intent=intent,
        )

    # -------- 改写 --------
    def _rewrite(self, query: str, history: list[dict[str, str]]) -> str:
        if not history:
            return query
        hist_text = "\n".join(f"{m['role']}: {m['content']}" for m in history)
        prompt = (
            "你是查询改写助手。根据对话历史,把下面用户的最新问题补全指代词、省略的主语,"
            "改写成独立、完整、明确的问题。\n"
            f"对话历史:\n{hist_text}\n\n"
            f"最新问题: {query}\n\n"
            "只输出改写后的问题本身,不要任何解释。"
        )
        out = self._llm.complete(prompt, temperature=0.1, max_tokens=200)
        return out.strip().strip('"').strip("'") or query

    # -------- 意图识别 --------
    def _intent(self, query: str) -> str:
        prompt = (
            "判断下面这个问题的意图类别,只能从以下 5 个里选一个:\n"
            f"{', '.join(INTENT_LABELS)}\n\n"
            f"问题: {query}\n\n"
            "只输出标签名,不要其它内容。"
        )
        out = self._llm.complete(prompt, temperature=0.0, max_tokens=20).strip().lower()
        return out if out in INTENT_LABELS else "factual"

    # -------- 扩展 --------
    def _expand(self, query: str) -> list[str]:
        prompt = (
            "你是查询扩展助手。围绕用户问题生成 3 个语义相关但表述不同的扩展问题,"
            "用来提升检索召回。每行一个问题,不要编号,不要解释。\n\n"
            f"原问题: {query}\n\n"
            "扩展问题:"
        )
        out = self._llm.complete(prompt, temperature=0.5, max_tokens=300)
        items = [line.strip().lstrip("0123456789.、) ").strip() for line in out.splitlines() if line.strip()]
        # 去重 + 去掉跟原问题相同的
        seen = {query}
        uniq = []
        for it in items:
            if it and it not in seen:
                uniq.append(it)
                seen.add(it)
        return uniq[:3] or [query]
