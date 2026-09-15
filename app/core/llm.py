"""LLM 客户端 —— 单一职责:用 OpenAI 兼容协议调 MiniMax M3,清洗 <think> 块。

为什么用 OpenAILike 而非裸 requests:
- /v1/chat/completions 跟 OpenAI 协议兼容,直接复用 llama-index 的客户端最省事。
- 唯一需要后处理的是 M3 会输出 <think>...</think> 推理块,要在这里一并剥掉,避免上游收到噪声。
"""
from __future__ import annotations

import re
from typing import Optional, List, Dict

from llama_index.core.llms import ChatMessage
from llama_index.llms.openai_like import OpenAILike

from app.core.config import Config

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_thinking(text: str) -> str:
    """去掉 M3 推理时输出的 <think>...</think> 块,返回剩余正文。"""
    if not text:
        return text
    cleaned = _THINK_RE.sub("", text).strip()
    return cleaned or text.strip()


class LLMClient:
    """MiniMax M3 对话客户端。所有 chat 调用都走这里,方便换模型时只动一个文件。"""

    def __init__(self, model: Optional[str] = None, timeout: int = 120):
        self._llm = OpenAILike(
            model=model or Config.LLM_MODEL,
            api_key=Config.MINIMAX_API_KEY,
            api_base=Config.MINIMAX_BASE_URL,
            is_chat_model=True,
            timeout=timeout,
        )

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.3, max_tokens: int = 1024) -> str:
        """messages: [{"role": "system|user|assistant", "content": "..."}]"""
        chat_msgs = [ChatMessage(role=m["role"], content=m["content"]) for m in messages]
        resp = self._llm.chat(chat_msgs, temperature=temperature, max_tokens=max_tokens)
        return strip_thinking(resp.message.content or "")

    def complete(self, prompt: str, temperature: float = 0.3, max_tokens: int = 1024) -> str:
        """单条 prompt 直接调(给意图识别 / 改写这种短任务用)。"""
        resp = self._llm.complete(prompt, temperature=temperature, max_tokens=max_tokens)
        return strip_thinking(resp.text or "")