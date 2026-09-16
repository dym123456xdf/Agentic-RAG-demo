"""Embedding 适配器 —— 单一职责:按 EMBEDDING_PROVIDER 把文本转成向量。

- MiniMaxEmbedding:embo-01,私有协议(请求体 texts/type,响应体 vectors[],GroupId 走 URL query),
  封死差异,上游无感知。
- ZhipuEmbedding:Embedding-3,OpenAI 兼容 /embeddings,dimensions 可选 256/512/1024/2048(默认 1024)。
- get_embedding():唯一入口,按 Config.EMBEDDING_PROVIDER 分发;上游(indexer)不感知具体实现。

注意:切换 provider = 更换向量空间,必须清空 Milvus collection 重建。
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


class ZhipuEmbedding(BaseEmbedding):
    """智谱 Embedding-3 适配器(OpenAI 兼容协议,自定义维度)。

    API:POST {GLM_BASE_URL}/embeddings,请求体 {model, input[], dimensions},
    响应体 {"data": [{"embedding": [...]}]} —— 与 OpenAI /v1/embeddings 同构。
    复用 GLM_API_KEY / GLM_BASE_URL,与对话模型同一套凭据。
    """

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 60,
    ):
        if not (api_key or Config.GLM_API_KEY):
            raise RuntimeError(
                "EMBEDDING_PROVIDER=glm 需要配置 GLM_API_KEY(智谱开放平台或 Z.ai 的 API Key,"
                "见项目根 .env)。"
            )
        super().__init__(model_name=model_name or Config.EMBEDDING_MODEL, embed_batch_size=10)
        self._api_key = api_key or Config.GLM_API_KEY
        self._url = (base_url or Config.GLM_BASE_URL).rstrip("/") + "/embeddings"
        self._timeout = timeout

    def _call(self, texts: list[str]) -> list[list[float]]:
        resp = requests.post(
            self._url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model_name,
                "input": texts,
                "dimensions": Config.EMBEDDING_DIM,
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("error"):
            raise RuntimeError(f"embedding 调用失败: {body['error']}")
        vectors: list[list[float]] = [item["embedding"] for item in body["data"]]
        return vectors

    # ============== BaseEmbedding 必须实现的钩子 ==============
    def _get_query_embedding(self, query: str) -> list[float]:
        return self._call([query])[0]

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._call([text])[0]

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return self._get_text_embedding(text)


def get_embedding() -> BaseEmbedding:
    """按 EMBEDDING_PROVIDER 返回对应的 embedding 实例(上游唯一入口)。"""
    if Config.EMBEDDING_PROVIDER == "minimax":
        return MiniMaxEmbedding()
    if Config.EMBEDDING_PROVIDER == "glm":
        return ZhipuEmbedding()
    raise RuntimeError(
        f"不支持的 EMBEDDING_PROVIDER: {Config.EMBEDDING_PROVIDER}(可选 minimax / glm)"
    )
