"""MiniMax embedding 适配器 —— 单一职责:把文本转成 1536 维向量。

为什么不能直接用 OpenAILikeEmbedding:
- MiniMax 的 /v1/embeddings 协议跟 OpenAI 不兼容:请求体用 texts/type,响应体用 vectors[],GroupId 必须走 URL query。
- 直接用 OpenAI 风格封装会静默返回空向量,数据进了 Milvus 但全是 0,检索永远召回 0 条。
- 这一个文件把这层差异封死,上游一切代码不需要知道 MiniMax 的怪协议。
"""
from __future__ import annotations

import requests
from llama_index.core.embeddings import BaseEmbedding

from app.core.config import Config


class MiniMaxEmbedding(BaseEmbedding):
    """MiniMax embo-01 的 llama-index 嵌入适配器。"""

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        group_id: str | None = None,
        timeout: int = 60,
    ):
        # embed_batch_size 是 BaseEmbedding 要求的入参,这里给 10,平衡吞吐和超时
        super().__init__(model_name=model_name or Config.EMBEDDING_MODEL, embed_batch_size=10)

        self._api_key = api_key or Config.MINIMAX_API_KEY
        # base_url 兼容两种写法:带 /v1 后缀 / 不带,统一剥掉再加 /v1/embeddings
        base = (base_url or Config.MINIMAX_BASE_URL).rstrip("/")
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        self._url = base + "/v1/embeddings"

        self._group_id = group_id or Config.MINIMAX_GROUP_ID
        self._timeout = timeout

    # ============== MiniMax 私有协议 ==============
    def _call(self, texts: list[str], type_: str) -> list[list[float]]:
        """type_ = "db" 用于入库,"query" 用于检索。两套编码空间,混用会召回率暴跌。"""
        resp = requests.post(
            self._url,
            params={"GroupId": self._group_id},
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.model_name, "type": type_, "texts": texts},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("base_resp", {}).get("status_code", 0) != 0:
            raise RuntimeError(f"embedding 调用失败: {body}")
        vectors: list[list[float]] = body["vectors"]
        return vectors

    # ============== BaseEmbedding 必须实现的钩子 ==============
    def _get_query_embedding(self, query: str) -> list[float]:
        """检索时用,type=query。"""
        return self._call([query], type_="query")[0]

    def _get_text_embedding(self, text: str) -> list[float]:
        """入库时用,type=db。"""
        return self._call([text], type_="db")[0]

    # async 钩子 —— llama-index 在某些路径会异步调用,这里直接走同步实现(够用)
    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return self._get_text_embedding(text)
