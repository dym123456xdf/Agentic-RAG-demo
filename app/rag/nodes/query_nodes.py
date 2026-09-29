"""查询图 8 节点 —— 预处理 → 按搜索模式互斥路由到单类召回 → RRF 融合 → 断崖重排 → 生成。

并发模型(搜索模式互斥路由,2026-09-28 起):
- preprocess 之后由 LangGraph conditional_edges 按 search_mode 互斥扇出:
  kb  → embedding_search +(HYDE_ENABLED 且 intent ∈ {factual, explanatory} 时)hyde_search
  web → web_search(仅此一路)
  xhs → xhs_search(仅此一路)
  外部模式(web / xhs)完全不查本地库;kb 模式不发起外部调用。
- intent == chitchat(寒暄/闲聊)时任何模式都不走任何召回,直达 cliff_rerank(空跑)
  → generate 走闲聊分支直接对话 —— 不是所有输入都需要 RAG 检索。
- 挂载路均汇向 rrf_fuse(模式内融合)→ cliff_rerank → generate。
- web_search 与 xhs_search 是异步节点(async def process),其它节点同步。
  LangGraph 对 sync/async node 都原生支持;BaseNode.__call__ 自动分流。

⚠️ 节点一律「增量返回」(只返回本节点写入的 key,不要返回整个 state):
  并行扇出的多个节点处于同一 superstep,若都返回完整 state,会对 session_id 等公共 key
  并发写,触发 InvalidUpdateError(LastValue channel 只接受单写者)。

外部召回(web / xhs)的降级语义:
- 节点内全捕异常 → 空 docs + warning 日志,图继续;按空召回走重排与生成,
  答案如实说「不知道」,不编造(BaseNode 包装只用于本路失败不该终止整图)。

流式说明:llama-index 的 LLMClient 不发 LangChain 事件,astream_events 拿不到 token 级
增量 —— 流式由 pipeline.query_stream 跑「检索子图」后在图外用 LLMClient.stream_chat 产出,
generate 节点只服务非流式整图路径。
"""
from __future__ import annotations

import asyncio
import hashlib
import re

from sentence_transformers import CrossEncoder

from app.core import bge_embedding, mcp_client, milvus_hybrid
from app.core.config import Config
from app.core.llm import LLMClient
from app.rag.base import BaseNode, QueryProcessError
from app.rag.state import QueryGraphState

# 小红书 MCP 调用超时上限(秒):无头浏览器搜索可能耗时数十秒;
# 低于常见 SSE 代理空闲超时,超时与其它异常同路降级空路(design D2)。
_XHS_TIMEOUT_S = 60


# ========== NodePreprocess ==========

INTENT_LABELS = ["factual", "explanatory", "comparison", "creative", "chitchat"]
HISTORY_WINDOW = 3  # 与旧 pre_query 对齐


class NodePreprocess(BaseNode[QueryGraphState]):
    """预处理:多轮改写 + 意图识别(5 类)。三步合一,省一次 LLM 往返。"""
    name = "preprocess"
    flow = "query"

    def __init__(self):
        super().__init__()
        self._llm = LLMClient(role="fast")

    def process(self, state: QueryGraphState) -> QueryGraphState:
        query = state.get("original_query", "").strip()
        history = (state.get("history") or [])[-HISTORY_WINDOW * 2:]
        # 改写
        rewritten = self._rewrite(query, history)
        # 意图
        intent = self._intent(rewritten)
        # ⚠️ 增量返回:preprocess 之后多路召回节点并行执行,若这里返回完整 state,
        # 同一 superstep 多节点写同一 key 会触发 InvalidUpdateError(LastValue channel)。
        return {"rewritten_query": rewritten, "intent": intent}

    def _rewrite(self, query: str, history: list[dict]) -> str:
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
        out = self._llm.complete(prompt, temperature=0.1, max_tokens=200).strip().strip('"').strip("'")
        return out or query

    def _intent(self, query: str) -> str:
        prompt = (
            "判断下面用户输入的意图类别,只能从以下 5 个里选一个:\n"
            "factual(查具体事实/数据)、explanatory(要原理解释)、comparison(要对比)、"
            "creative(要创作)、chitchat(寒暄/问候/闲聊,不寻求知识内容,如:你好、在吗、谢谢、再见)\n\n"
            f"用户输入: {query}\n\n"
            "只输出标签名,不要其它内容。"
        )
        out = self._llm.complete(prompt, temperature=0.0, max_tokens=20).strip().lower()
        return out if out in INTENT_LABELS else "factual"


# ========== NodeEmbeddingSearch ==========

class NodeEmbeddingSearch(BaseNode[QueryGraphState]):
    """向量召回:dense + sparse 混合检索,产出 embedding_chunks。"""
    name = "embedding_search"
    flow = "query"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        query = state.get("rewritten_query", "")
        if not query:
            return {"embedding_chunks": []}
        dense = bge_embedding._encode_dense([query])[0]
        sparse = bge_embedding.encode_sparse(query)
        hits = milvus_hybrid.hybrid_search(dense, sparse, top_k=Config.TOP_K)
        # 增量返回:并行节点只写自己的 key,避免 LastValue channel 并发写冲突
        return {"embedding_chunks": hits}


# ========== NodeHydeSearch ==========

class NodeHydeSearch(BaseNode[QueryGraphState]):
    """HyDE 假设性文档检索:LLM 生成假设答案,与 rewritten 拼接后走同一 hybrid_search。"""
    name = "hyde_search"
    flow = "query"

    def __init__(self):
        super().__init__()
        self._llm = LLMClient(role="fast")

    def process(self, state: QueryGraphState) -> QueryGraphState:
        query = state.get("rewritten_query", "")
        if not query:
            return {"hyde_embedding_chunks": []}
        prompt = (
            "你是该领域专家。直接给出下面问题最可能的标准答案,"
            "无需真实检索,只基于你的领域知识给出 50-200 字的回答。\n\n"
            f"问题: {query}\n\n"
            "直接给出答案:"
        )
        hyde_doc = self._llm.complete(prompt, temperature=0.3, max_tokens=400).strip()
        combined = f"{query} {hyde_doc}".strip()
        dense = bge_embedding._encode_dense([combined])[0]
        sparse = bge_embedding.encode_sparse(combined)
        hits = milvus_hybrid.hybrid_search(dense, sparse, top_k=Config.TOP_K)
        # 增量返回:与 embedding_search 并行,只写自己的 key
        return {"hyde_embedding_chunks": hits}


# ========== NodeWebSearch ==========

class NodeWebSearch(BaseNode[QueryGraphState]):
    """MCP Web 搜索:stdio 拉起 python -m mcp_server,调 web_search 工具。

    异步节点:process 是 async def,基类 __call__(协程)直接 await 它;LangGraph ainvoke /
    astream 会在事件循环内 await,不阻塞。
    """
    name = "web_search"
    flow = "query"

    async def process(self, state: QueryGraphState) -> QueryGraphState:
        query = state.get("rewritten_query", "")
        if not query:
            return {"web_search_docs": []}
        try:
            items = await mcp_client.call_tool("web_search", {"query": query, "count": 5})
        except Exception as e:
            self.logger.warning(f"web_search 失败: {e};降级为空")
            items = []
        # 规范化字段,加 source_type=web;增量返回(与另两路并行)
        return {"web_search_docs": [
            {
                "text": it.get("snippet", ""),
                "doc_name": it.get("title", ""),
                "file_dir": it.get("url", ""),
                "chunk_idx": 0,
                "metadata": {"source_type": "web"},
                "score": 1.0,
                "source_type": "web",
            }
            for it in items
        ]}


# ========== NodeXhsSearch ==========

def _normalize_xhs_item(it: dict) -> dict | None:
    """把 search_feeds 返回的单条 feed 规范化为与 Web 召回同形的文档。

    防御性字段提取(design D4):字段名以实测为准,逐字段 fallback。
    实测结构(feed item):{id, xsecToken, modelType, noteCard:{displayTitle, desc?, user{nickname}, ...}}
    - text:   标题 + 摘要(desc 若有)
    - doc_name: 标题
    - file_dir: https://www.xiaohongshu.com/explore/<id>
    - metadata: source_type=xhs + feed_id + xsec_token(token 留给未来详情补全)
    返回 None 表示该条无效(无 id / 无标题),调用方跳过。
    """
    fid = it.get("id") or it.get("note_id") or ""
    if not fid:
        return None
    card = it.get("noteCard") or {}
    title = (card.get("displayTitle") or card.get("title") or it.get("title") or "").strip()
    desc = (card.get("desc") or it.get("desc") or "").strip()
    if not title:
        return None
    text = f"{title} {desc}".strip()
    url = f"https://www.xiaohongshu.com/explore/{fid}"
    metadata = {
        "source_type": "xhs",
        "feed_id": fid,
        "xsec_token": it.get("xsecToken") or it.get("xsec_token") or "",
        "author": (card.get("user") or {}).get("nickname") or (card.get("user") or {}).get("nickName") or "",
    }
    return {
        "text": text,
        "doc_name": title,
        "file_dir": url,
        "chunk_idx": 0,
        "metadata": metadata,
        "score": 1.0,
        "source_type": "xhs",
    }


class NodeXhsSearch(BaseNode[QueryGraphState]):
    """小红书 MCP 召回:Streamable HTTP 调外部 xiaohongshu-mcp 的 search_feeds 工具。

    仅在 search_mode == "xhs" 且 XHS_MCP_ENABLED 时挂载,与查询意图无关(用户显式选择
    优先)。异步节点:调 mcp_client.call_tool_http(每次独立建连),asyncio.wait_for 60s
    兜底(design D2)。节点内全捕异常 → 空 xhs_search_docs + warning,图继续(降级空路,
    不阻断整图,不编造答案)——与 NodeWebSearch 同款语义。
    """
    name = "xhs_search"
    flow = "query"

    async def process(self, state: QueryGraphState) -> QueryGraphState:
        query = state.get("rewritten_query", "")
        if not query:
            return {"xhs_search_docs": []}
        # 取鉴权头(可选 Bearer;未配置则不携带)
        headers = None
        if Config.XHS_MCP_TOKEN:
            headers = {"Authorization": f"Bearer {Config.XHS_MCP_TOKEN}"}
        try:
            raw = await asyncio.wait_for(
                mcp_client.call_tool_http(
                    Config.XHS_MCP_URL, "search_feeds", {"keyword": query}, headers=headers,
                ),
                timeout=_XHS_TIMEOUT_S,
            )
        except Exception as e:
            self.logger.warning(f"xhs_search 失败: {e};降级为空(服务未启动/登录态失效/超时)")
            return {"xhs_search_docs": []}
        # 防御性提取:search_feeds 返回 {"feeds": [...], "count": N}
        feeds = raw.get("feeds", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        docs = [d for d in (_normalize_xhs_item(it) for it in feeds[:Config.XHS_SEARCH_LIMIT]) if d]
        # 增量返回:只写本路 key(与 embedding/hyde/web 互斥,不会同时并行)
        return {"xhs_search_docs": docs}


# ========== NodeRrfFuse ==========

class NodeRrfFuse(BaseNode[QueryGraphState]):
    """RRF 倒数排名融合(模式内):只融合当前搜索模式挂载的各路,等权 k=60。

    搜索模式互斥后,任一时刻至多两路同时有结果(kb → embedding + hyde),
    web / xhs 为单路(退化为按原顺序的重排)。按 search_mode 取路径表,不再三路同框。
    """
    name = "rrf_fuse"
    flow = "query"

    RR_WEIGHTS = {"embedding": 1.0, "hyde": 1.0, "web": 1.0, "xhs": 1.0}

    # 模式 → 该模式下挂载的召回路(key: 路径名 / value: 状态字段名)
    _PATHS_BY_MODE: dict[str, dict[str, str]] = {
        "kb": {"embedding": "embedding_chunks", "hyde": "hyde_embedding_chunks"},
        "web": {"web": "web_search_docs"},
        "xhs": {"xhs": "xhs_search_docs"},
    }

    def process(self, state: QueryGraphState) -> QueryGraphState:
        mode = state.get("search_mode", "kb")
        path_map = self._PATHS_BY_MODE.get(mode, self._PATHS_BY_MODE["kb"])
        paths: dict[str, list[dict]] = {
            p: (state.get(field) or []) for p, field in path_map.items()
        }
        scores: dict[str, float] = {}
        docs: dict[str, dict] = {}
        k = Config.RRF_K

        for path, items in paths.items():
            if not items:
                continue
            w = self.RR_WEIGHTS.get(path, 1.0)
            # 各路按 score 降序(milvus_hybrid 已把 distance 反转为 score)
            sorted_items = sorted(items, key=lambda x: x.get("score", 0.0), reverse=True)
            for rank, item in enumerate(sorted_items, start=1):
                doc_id = _doc_id_of(item)
                scores[doc_id] = scores.get(doc_id, 0.0) + w / (k + rank)
                if doc_id not in docs:
                    docs[doc_id] = dict(item)
                    docs[doc_id]["rrf_score"] = scores[doc_id]
                else:
                    docs[doc_id]["rrf_score"] = scores[doc_id]

        fused = sorted(docs.values(), key=lambda d: d["rrf_score"], reverse=True)
        # 增量返回:只写融合结果
        return {"rrf_chunks": fused}


def _doc_id_of(item: dict) -> str:
    """给 item 一个稳定 doc_id:web 文档用 url,xhs 用笔记链接,向量文档用 Milvus id 或 text hash。"""
    if item.get("id"):
        return str(item["id"])
    text = item.get("text", "")
    st = item.get("source_type")
    if st == "web" and item.get("file_dir"):
        return f"web::{item['file_dir']}"
    if st == "xhs" and item.get("file_dir"):
        return f"xhs::{item['file_dir']}"
    return hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()


# ========== NodeCliffRerank ==========

class NodeCliffRerank(BaseNode[QueryGraphState]):
    """BGE 重排 + 断崖检测动态截断(绝对 + 相对双阈值)。"""
    name = "cliff_rerank"
    flow = "query"

    _reranker: CrossEncoder | None = None  # 跨实例共享

    @classmethod
    def _get_reranker(cls) -> CrossEncoder:
        if cls._reranker is None:
            import torch
            device = "mps" if torch.backends.mps.is_available() else "cpu"
            cls._reranker = CrossEncoder(Config.RERANK_MODEL, device=device)
        return cls._reranker

    def process(self, state: QueryGraphState) -> QueryGraphState:
        chunks = state.get("rrf_chunks") or []
        query = state.get("original_query", "") or state.get("rewritten_query", "")
        if not chunks:
            return {"reranked_docs": []}

        # 1. BGE 重排打分
        try:
            reranker = self._get_reranker()
            pairs = [(query, c.get("text", "")) for c in chunks]
            scores = reranker.predict(pairs, show_progress_bar=False).tolist()
        except Exception as e:
            self.logger.warning(f"rerank fallback to rrf_score: {e}")
            scores = [float(c.get("rrf_score", 0.0)) for c in chunks]

        scored = sorted(
            [
                {**c, "score": float(s)}
                for c, s in zip(chunks, scores, strict=False)
            ],
            key=lambda x: x["score"],
            reverse=True,
        )

        # 2. 断崖检测
        cut = _cliff_cut(
            [s["score"] for s in scored],
            Config.RERANK_GAP_ABS,
            Config.RERANK_GAP_RATIO,
            Config.RERANK_MIN_TOPK,
            Config.RERANK_MAX_TOPK,
        )
        reranked = scored[:cut]

        # 3. 加 confidence(sigmoid)便于前端低置信度提示
        for r in reranked:
            r["confidence"] = _sigmoid(r["score"])
            r["source_type"] = r.get("source_type", "vector")
        # 增量返回:只写重排结果
        return {"reranked_docs": reranked}


def _cliff_cut(scores: list[float], gap_abs: float, gap_ratio: float,
               min_topk: int, max_topk: int) -> int:
    """断崖检测首次触发即截断;最终 cut 收敛到 [min_topk, max_topk]。"""
    n = len(scores)
    if n == 0:
        return 0
    cut = n
    for i in range(1, n):
        prev, cur = scores[i - 1], scores[i]
        if prev - cur >= gap_abs:
            cut = i
            break
        if prev > 0 and (prev - cur) / prev >= gap_ratio:
            cut = i
            break
    return max(min_topk, min(cut, max_topk))


def _sigmoid(x: float) -> float:
    import math
    try:
        return round(1.0 / (1.0 + math.exp(-x)), 4)
    except OverflowError:
        return 0.0 if x < 0 else 1.0


# ========== NodeGenerate ==========

# 生成节点的系统提示与图片引用正则(模块级:节点内非流式与 pipeline 流式两路共用)
SYSTEM = (
    "你是一个严谨的个人知识库助手。回答用户问题时,只能依据下方提供的【参考资料】;"
    '如果资料里没有答案,就明确说"我不知道,资料里没提到",不要编造。'
    "回答完简要回答后,用一句话给出最相关的 1-3 条来源编号。"
    "参考资料中的图片引用(形如 ![...](/converted/...) 的 markdown 语法)必须逐字原样保留进答案,"
    "不得改写、缩写或编造任何图片路径;参考资料里没有图片引用时,答案里不得出现任何图片语法。"
)

# 闲聊分支(intent=chitchat)的系统提示:不查知识库,直接对话
CHITCHAT_SYSTEM = (
    "你是个人知识库助手。用户此刻在寒暄或闲聊,不是在查询知识库,"
    "请友好、自然、简短地回应;不要提及参考资料,不要编造知识库内容;"
    "若用户顺带问了知识类问题,可以简单回应并提示可以帮忙查询知识库。"
)

_IMG_REF_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")


class NodeGenerate(BaseNode[QueryGraphState]):
    """LLM 生成答案;支持流式(is_stream=True)与一次性输出。"""
    name = "generate"
    flow = "query"

    def __init__(self):
        super().__init__()
        self._llm = LLMClient(role="main")

    @staticmethod
    def build_chitchat_messages(query: str, history: list[dict]) -> list[dict[str, str]]:
        """闲聊分支的消息装配:带最近几轮历史,无参考资料约束,自然对话。"""
        messages: list[dict[str, str]] = [{"role": "system", "content": CHITCHAT_SYSTEM}]
        messages += [
            {"role": m["role"], "content": m["content"]}
            for m in (history or [])[-HISTORY_WINDOW * 2:]
        ]
        messages.append({"role": "user", "content": query})
        return messages

    @staticmethod
    def build_messages(query: str, docs: list[dict]) -> list[dict[str, str]]:
        """装配 system + user 消息(节点内非流式与 pipeline 流式两路共用)。

        片段正文截 200 字符入 prompt,markdown 图片引用整条抽出追加(防 URL 被
        截断后 LLM 脑补路径)—— 与旧 generator 的行为保持一致。
        """
        blocks: list[str] = []
        for i, d in enumerate(docs, 1):
            source = d.get("doc_name") or "unknown"
            doc_id = d.get("metadata", {}).get("doc_id", "")
            content = (d.get("text") or "").strip()
            snippet = content.replace("\n", " ")[:200]
            img_refs = list(dict.fromkeys(_IMG_REF_RE.findall(content)))
            if img_refs:
                snippet += "\n[本片段完整图片引用,回答时原样保留: " + " ".join(img_refs) + "]"
            blocks.append(
                f"[{i}] (来源:{source} | doc_id={doc_id} | 相关度:{d.get('score', 0.0):.3f})\n{snippet}..."
            )
        prompt = (
            f"用户问题: {query}\n\n"
            f"【参考资料】\n{chr(10).join(blocks)}\n\n"
            "请基于上面的资料给出回答。"
        )
        return [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ]

    def process(self, state: QueryGraphState) -> QueryGraphState:
        query = state.get("rewritten_query") or state.get("original_query", "")
        docs = state.get("reranked_docs") or []
        # 闲聊分支:不查知识库,直接对话(带历史,无参考资料约束)
        if state.get("intent") == "chitchat":
            messages = self.build_chitchat_messages(query, state.get("history") or [])
            answer = self._llm.chat(messages, temperature=0.5, max_tokens=300)
            return {"answer": answer, "prompt": messages[-1]["content"]}
        if not docs:
            return {"answer": "我不知道,资料里没提到。", "prompt": ""}
        messages = self.build_messages(query, docs)
        # 非流式整图路径;流式由 pipeline.query_stream 在图外用 stream_chat 逐块产出
        answer = self._llm.chat(messages, temperature=0.2, max_tokens=800)
        # 增量返回:只写本节点产出
        return {"answer": answer, "prompt": messages[1]["content"]}


# 供 LangGraph 图装配使用
def route_after_preprocess(state: QueryGraphState) -> list[str]:
    """preprocess 节点之后,按搜索模式 + 意图 + 开关互斥地返回要走的下游节点名列表。

    语义(design D5/D6,搜索模式互斥路由):
    - chitchat(寒暄/闲聊)在任何模式下都直达 cliff_rerank:全部召回路跳过(省向量检索 +
      HyDE / 外部调用),cliff_rerank 对空输入是 no-op,汇合后 generate 走闲聊分支直接对话。
    - 其余意图按 search_mode 互斥挂载:
        kb  → embedding_search +(HYDE_ENABLED 且 intent ∈ {factual, explanatory} 时)hyde_search
        web → 仅 web_search
        xhs → 仅 xhs_search
    外部模式(web / xhs)完全不查本地库;kb 模式不发起外部调用。外部路不因意图被拦截
    (用户显式选择优先),HyDE 的意图规则保留在 kb 模式内(它是向量检索的质量增强)。
    非法 search_mode 回退 kb(防御:API 层已拒收,这里是兜底)。
    """
    intent = state.get("intent", "factual")
    if intent == "chitchat":
        return ["cliff_rerank"]
    mode = state.get("search_mode", "kb")
    if mode == "web":
        return ["web_search"]
    if mode == "xhs":
        return ["xhs_search"]
    # kb(默认 / 未知值兜底):向量 + 按现行规则的 HyDE
    targets = ["embedding_search"]
    if Config.HYDE_ENABLED and intent in ("factual", "explanatory"):
        targets.append("hyde_search")
    return targets
