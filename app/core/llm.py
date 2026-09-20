"""LLM 客户端 —— 单一职责:用 OpenAI 兼容协议调 MiniMax M3,清洗 think 推理块。

为什么用 OpenAILike 而非裸 requests:
- /v1/chat/completions 跟 OpenAI 协议兼容,直接复用 llama-index 的客户端最省事。
- 唯一需要后处理的是 M3 会输出 think 推理块(开/闭标签形如 < 后接 think),要在这里一并剥掉,避免上游收到噪声。
"""
from __future__ import annotations

import re
from typing import Iterator

from llama_index.core.llms import ChatMessage
from llama_index.llms.openai_like import OpenAILike

from app.core.config import Config

# think 标签常量:开标签用 chr(60) 拼装,不写字面量(开标签字面序列会被部分工具链当
# think 泄漏块脱敏,写进去就变空格;闭标签无此问题,直接写字面)
_TK_OPEN = chr(60) + "think"
_TK_CLOSE = chr(60) + "/think>"
_THINK_RE = re.compile(_TK_OPEN + r".*?" + _TK_CLOSE, re.DOTALL)


def strip_thinking(text: str) -> str:
    """去掉 M3 推理时输出的 think 块,返回剩余正文。

    不再做"cleaned 为空时回退原文本"的兜底 —— 那会把完整的 think 块原样泄露出去
    (实测 M3 改写任务出现过:cleaned 整个就是空,回退原文本就只剩 think 块)。
    上游 _rewrite / _intent / _expand 各自有空字符串的兜底语义(回退原 query / "factual" / []),
    此处契约只管"剥 think 块,剥完返回剩余(可能为空)"。
    """
    if not text:
        return text
    return _THINK_RE.sub("", text).strip()


class ThinkStreamFilter:
    """strip_thinking 的流式安全版:逐块 delta 喂入,即时吐安全文本。

    思路:持有缓冲,每 push 一次 ——
    1. 剥掉缓冲里**已闭合**的 think 块(正则非贪婪,没闭合的块不会被误剥);
    2. 缓冲尾部若停在小于号开头且是 think 开标签的前缀(块可能还在生长),滞留在缓冲不发出;
       普通小于号(正文 "3 < 5")不满足前缀条件,照常即时发出,不影响流式及时性。
    流结束调 flush():残留未闭合的 think 段直接截掉(推理没写完整,不留给用户)。
    """

    def __init__(self) -> None:
        self._buf = ""

    def push(self, chunk: str) -> str:
        self._buf += chunk
        self._buf = _THINK_RE.sub("", self._buf)
        i = self._buf.rfind(chr(60))
        if i != -1:
            tail = self._buf[i:]
            # 滞留四种情况:
            # 1) tail 以完整开标签开头(块进行中,等闭标签)
            # 2) tail 以完整闭标签开头(孤立的闭合标签,原文语义下也会保留,先滞留再议)
            # 3) tail 是开标签的严格前缀(开标签还没长完,如只剩 "<", "<th")
            # 4) tail 是闭标签的严格前缀(闭标签跨 chunk 长到一半,如 " think")
            # 其余尾部 "<"(正文 "3 < 5")四种都不满足,照常即时发出。
            if (tail.startswith(_TK_OPEN) or tail.startswith(_TK_CLOSE)
                    or _TK_OPEN.startswith(tail) or _TK_CLOSE.startswith(tail)):
                emit, self._buf = self._buf[:i], tail
            else:
                emit, self._buf = self._buf, ""
        else:
            emit, self._buf = self._buf, ""
        return emit

    def flush(self) -> str:
        """流结束:截掉未闭合的 think 段,再削掉尾部半个标签片段(如孤立的 " think")。"""
        buf = self._buf
        m = buf.find(_TK_OPEN)
        if m != -1:
            buf = buf[:m]
        for tag in (_TK_OPEN, _TK_CLOSE):
            for k in range(len(tag) - 1, 0, -1):
                if buf.endswith(tag[:k]):
                    buf = buf[: len(buf) - k]
                    break
            else:
                continue
            break
        self._buf = ""
        return buf


class LLMClient:
    """对话客户端。凭据按 Config.LLM_PROVIDER 切换(minimax / glm),换模型只动 .env。

    role 双档位:minimax 下两档同模型;glm 下 main=GLM_MODEL(生成),
    fast=GLM_FAST_MODEL(预处理,默认免费档 glm-4.7-flash)。
    """

    def __init__(self, model: str | None = None, role: str = "main", timeout: int = 120):
        cred = Config.llm_credentials(role=role)
        self._llm = OpenAILike(
            model=model or cred["model"],
            api_key=cred["api_key"],
            api_base=cred["base_url"],
            is_chat_model=True,
            timeout=timeout,
        )

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.3, max_tokens: int = 1024) -> str:
        """messages: [{"role": "system|user|assistant", "content": "..."}]"""
        chat_msgs = [ChatMessage(role=m["role"], content=m["content"]) for m in messages]
        resp = self._llm.chat(chat_msgs, temperature=temperature, max_tokens=max_tokens)
        return strip_thinking(resp.message.content or "")

    def complete(self, prompt: str, temperature: float = 0.3, max_tokens: int = 1024) -> str:
        """单条 prompt 直接调(给意图识别 / 改写 / 扩展这种短任务用)。"""
        resp = self._llm.complete(prompt, temperature=temperature, max_tokens=max_tokens)
        return strip_thinking(resp.text or "")

    def stream_chat(self, messages: list[dict[str, str]], temperature: float = 0.3,
                    max_tokens: int = 1024) -> Iterator[str]:
        """chat 的流式版:逐块 yield **增量**文本(含 think 块),清洗交给调用方(ThinkStreamFilter)。

        注意:OpenAILike 底层 stream_chat 的每个 chunk 是**截至当前的累计全文**
        (实测 M3:chunk 长度单调增),这里按"前缀已发过"取后缀当增量;
        若未来换成真增量协议的 provider,else 分支自动兼容,无需改调用方。
        """
        chat_msgs = [ChatMessage(role=m["role"], content=m["content"]) for m in messages]
        prev = ""
        for resp in self._llm.stream_chat(chat_msgs, temperature=temperature, max_tokens=max_tokens):
            text = (resp.message.content if resp.message is not None else None) or getattr(resp, "text", None) or ""
            if text.startswith(prev):
                delta = text[len(prev):]
                prev = text
            else:
                delta = text
                prev += text
            if delta:
                yield delta
