# Design: enterprise-rag-upgrade

> 本文件描述实现细节(架构图、状态契约、节点契约、算法)。能力边界与对外承诺请见 `proposal.md` 与 `specs/<cap>/spec.md`。

## 1. 总体架构

```
+----------------------- FastAPI ------------------------+
|  /upload  /converted  /chat  /sessions  /manage  ...   |
+------------------------+--+--+--+--+-------------------+
                         |  |  |  |  |
                         v  v  v  v  v
+---------------------- app.rag.pipeline --------------------+
|  LangGraph 薄壳:query() / query_stream() / ingest()      |
+----+----------------------------+---------------------+--+
     |                            |                     |
     v                            v                     v
+----+-----+               +-------+-------+     +-------+-------+
| 查询图   |               | 入库图       |     | 节点基类      |
| Query   |               | Ingest       |     | NodeBase(ABC) |
| Graph   |               | Graph        |     +---------------+
+----+----+               +-----+--------+              ^
     |                          |                       |
     v                          v                       |
+----+-------------+    +-------+----------+    +------+-------+
| 7 个查询节点     |    | 7 个入库节点     |    | 通用基类继承  |
| +----------+     |    |                  |    +--------------+
| preprocess|<---+ |    | entry            |
| embedding |    | |    | pdf_to_md        |
| hyde      |    | |    | md_img           |
| web       |    | |    | doc_split        |
| rrf       |    | |    | item_name        |
| rerank    |    | |    | bge_embedding    |
| generate  |    | |    | import_milvus    |
+----+-------+    | |    +------------------+
                 | |                      
                 v v                      
            +------+------+               
            | 状态契约     |               
            | TypedDict   |               
            +------+------+               
                   |                      
                   v                      
        +----------+-----------+          
        | 核心模块支撑          |          
        | llm / bge_embedding /|          
        | milvus_hybrid /      |          
        | minio_client /       |          
        | mcp_client / db      |          
        +----------------------+          
```

## 2. 入库图(IngestGraph)

### 2.1 节点顺序

```
+---------+    +-------------+    +----------+    +------------+
| entry   |--->| pdf_to_md   |--->| md_img   |--->| doc_split  |
| 入口    |    | MinerU 转换 |    | 图片处理 |    | 文档切分   |
+---------+    +-------------+    +----------+    +-----+------+
                                                        |
                                                        v
                                       +----------------+-------------+
                                       | item_name_recognition        |
                                       | 商品名识别(可选,LLM)         |
                                       +----------------+-------------+
                                                        |
                                                        v
                                       +----------------+-------------+
                                       | bge_embedding                |
                                       | BGE-M3 嵌入(dense+sparse)    |
                                       +----------------+-------------+
                                                        |
                                                        v
                                       +----------------+-------------+
                                       | import_milvus                |
                                       | 写入 Milvus hybrid collection|
                                       +------------------------------+
```

### 2.2 状态契约(`ImportGraphState`,TypedDict,total=False)

| 字段 | 类型 | 含义 |
|------|------|------|
| `task_id` | `str` | 任务追踪 ID,前端可据此看到节点日志 |
| `import_file_path` | `str` | MinIO 对象路径(`uploads/<name>`) |
| `pdf_path` | `str` | MinIO 中原始 PDF 路径 |
| `md_path` | `str` | MinIO 中 md 产物路径 |
| `file_dir` | `str` | 当前文件在 MinIO 的前缀(`converted/<stem>/`) |
| `file_title` | `str` | 文件标题(去扩展名) |
| `md_content` | `str` | 解析后的 md 全文 |
| `chunks` | `List[Dict]` | 切分后的块,字段含 `text`、`metadata`、`item_name` |
| `is_pdf_read_enabled` | `bool` | 是否启用 PDF 阅读(本期关) |
| `is_md_read_enabled` | `bool` | 是否启用 MD 阅读(本期开) |

默认状态由 `create_default_state(**overrides)` 工厂生成,避免全局污染。

### 2.3 节点契约(基类 `BaseNode`)

```python
class BaseNode(ABC, Generic[T]):
    name: str = "base_node"   # 子类覆盖
    flow: str = "base"        # 子类覆盖:"ingest" 或 "query",决定日志前缀

    def __init__(self):
        self.logger = logging.getLogger(f"{self.flow}.{self.name}")

    def __call__(self, state: T) -> T:           # LangGraph 同步调用入口
        try:
            self.logger.info(f"--- {self.name} 开始 ---")
            result = self.process(state)          # 子类核心逻辑
            self.logger.info(f"--- {self.name} 完成 ---")
            return result
        except Exception as e:
            self.logger.error(f"{self.name} 失败: {e}")
            raise IngestProcessError / QueryProcessError(...)

    # process 为 async def 时基类自动改走异步包装(_acall),
    # 供 web_search 等需 await MCP stdio 的节点使用
    @abstractmethod
    def process(self, state: T) -> T: ...
```

所有节点继承该基类,日志前缀按 `flow` 区分:`ingest.<name>` / `query.<name>`;节点一律**增量返回**(只写本节点产出的 key),避免并行扇出时并发写公共 key 触发 `InvalidUpdateError`。

## 3. 查询图(QueryGraph)

### 3.1 节点顺序与并行扇出

```
                 +----------------------+
                 | preprocess            |
                 | 改写 query / 意图识别 |
                 +----------+------------+
                            |
          chitchat? ────────┼──────── 否,按意图扇出
                            |          (寒暄/闲聊直达重排空跑,不查知识库)
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
+-------+-------+   +-------+-------+   +-------+-------+
| embedding    |   | hyde          |   | web_search    |
| 向量检索      |   | HyDE 假设检索 |   | MCP 网络搜索  |
| (非 chitchat |   | (factual /   |   | (factual 且   |
|  意图均挂载)  |   |  explanatory)|   |  web 标志)    |
+-------+-------+   +-------+-------+   +-------+-------+
        \                   |                   /
         \                  |                  /
          +-----------------+-----------------+
                            |
                            v
                   +--------+--------+
                   | rrf_fuse         |
                   | RRF 融合         |
                   | (k=60, 等权重)  |
                   +--------+--------+
                            |
                            v
                   +--------+--------+
                   | cliff_rerank     |
                   | 重排 + 断崖截断 |
                   +--------+--------+
                            |
                            v
                   +--------+--------+
                   | generate         |
                   | LLM 生成回答    |
                   | (chitchat 走闲聊 |
                   |  分支直接对话)   |
                   +-----------------+
```

### 3.2 状态契约(`QueryGraphState`,TypedDict,total=False)

| 字段 | 类型 | 含义 |
|------|------|------|
| `session_id` | `str` | 会话 ID |
| `message_id` | `str` | 当前消息 ID |
| `original_query` | `str` | 用户原始问题 |
| `rewritten_query` | `str` | 改写后查询 |
| `intent` | `str` | 意图标签:`factual` / `explanatory` / `chitchat` / `creative` |
| `item_name` | `str` | 上下文商品/主题名(可选) |
| `embedding_chunks` | `List[Dict]` | 向量召回原始结果 |
| `hyde_embedding_chunks` | `List[Dict]` | HyDE 召回原始结果 |
| `web_search_docs` | `List[Dict]` | Web 召回原始结果 |
| `rrf_chunks` | `List[Dict]` | RRF 融合后 |
| `reranked_docs` | `List[Dict]` | 重排+断崖后最终来源 |
| `prompt` | `str` | 装配后的 prompt |
| `answer` | `str` | LLM 生成的最终回答(流式片段累计) |
| `history` | `List[Dict]` | 会话历史(从 MySQL 注入) |
| `is_stream` | `bool` | 是否走流式 |

### 3.3 节点契约(查询图基类 `BaseNode`)

查询图节点复用同一 `BaseNode`(`app/rag/base.py`),仅日志前缀为 `query.<node_name>`。

### 3.4 并行扇出实现(LangGraph 模式)

```python
# preprocess 之后,LangGraph 从 preprocess 出条件边
workflow.add_conditional_edges(
    "preprocess",
    route_after_preprocess,                   # chitchat → ["cliff_rerank"](直达,跳过全部召回)
                                              # 其余 → ["embedding_search"] 或
                                              #   ["embedding_search","hyde_search"] 或
                                              #   ["embedding_search","hyde_search","web_search"]
    {
        "embedding_search": "embedding_search",
        "hyde_search":      "hyde_search",
        "web_search":       "web_search",
        "cliff_rerank":     "cliff_rerank",   # chitchat 直达目标
    },
)
# 三路都汇向 rrf_fuse
workflow.add_edge("embedding_search", "rrf_fuse")
workflow.add_edge("hyde_search",      "rrf_fuse")
workflow.add_edge("web_search",       "rrf_fuse")
```

`route_after_preprocess` 根据 `intent`、`HYDE_ENABLED`、`WEB_SEARCH_ENABLED` 返回要走的下游节点名列表,LangGraph 内部按边 fan-out 调度,rrf_fuse 等所有上游结束再触发;`chitchat` 直达 `cliff_rerank`(空输入 no-op)后由 generate 的闲聊分支直接对话。

## 4. LLM 客户端(保留现状)

`app/core/llm.py` 维持 llama-index `OpenAILike` 适配 `LLMClient`,不做改造。凭据按 `Config.LLM_PROVIDER` 切换,支持 `minimax` / `glm` / `agnes`(agnes-3.0-flash,单一 flash 档,main/fast 同模型),换模型只动 `.env`。LangGraph 节点直接同步 `self._llm.chat(...)` / `complete(...)` 复用现有能力(包括 `strip_thinking` 与 `ThinkStreamFilter`)。**不引入 LangChain ChatOpenAI**。

## 5. BGE-M3 嵌入适配(`app/core/bge_embedding.py`)

```python
class BGEEmbedding(BaseEmbedding):
    """llama-index 适配 BGE-M3,产出 dense(1024)+sparse 双向量。"""

    def __init__(self, model_name="BAAI/bge-m3", device="mps", dim=1024):
        from FlagEmbedding import BGEM3FlagModel
        self.model = BGEM3FlagModel(model_name, use_fp16=(device != "cpu"))
        self.dim = dim

    # llama-index 同步路径(查询 / 索引构建走这里)
    def _get_query_embedding(self, q): return self._embed(q)
    def _get_text_embedding(self, t):  return self._embed(t)
    def _get_text_embeddings(self, texts): return [self._embed(t) for t in texts]

    def _embed(self, text):
        out = self.model.encode(
            [text],
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        return out["dense_vecs"][0].tolist()  # dense(1024)

    # 稀疏向量由专用方法暴露给 Milvus hybrid_search 直接使用
    def encode_sparse(self, text) -> Dict[int, float]:
        out = self.model.encode(
            [text], return_dense=False, return_sparse=True,
        )
        return _csr_to_dict(out["lexical_weights"][0])
```

应用方式:

- **入库**:节点 `bge_embedding` 调 `encode_sparse(text)` 拿稀疏、`embed(text)` 拿 dense,同时灌进 Milvus。
- **查询**:节点 `embedding_search` 与 `hyde_search` 同样调两次,把两套向量塞进 `AnnSearchRequest` 数组。

实现注意:模块内模型为**进程级单例**(`get_model()`),加载与推理各持一把锁 —— macOS MPS 上并发推理会段错误,双锁保证串行;模型加载耗时较长(约 30s),首请求触发懒加载。

## 6. Milvus 混合检索(`app/core/milvus_hybrid.py`)

### 6.1 Collection schema

```
Collection: rag_kb_chunks
+-----------+------------------+----------+---------+
| 字段      | 类型             | 其他     | 说明    |
+-----------+------------------+----------+---------+
| id        | INT64            | PK,auto  | 主键    |
| text      | VARCHAR(4096)    |          | chunk 文本|
| dense     | FLOAT_VECTOR(1024)| COSINE  | BGE-M3 dense |
| sparse    | SPARSE_FLOAT_VECTOR| IP    | BGE-M3 learned sparse |
| doc_name  | VARCHAR(256)     |          | 源文件名 |
| file_dir  | VARCHAR(512)     |          | MinIO 前缀 |
| chunk_idx | INT64            |          | chunk 序号 |
| metadata  | JSON             | dynamic  | 其他元数据 |
+-----------+------------------+----------+---------+
索引:dense → HNSW(metric=COSINE, M=16, efConstruction=200)
     sparse → SPARSE_INVERTED_INDEX(metric=IP, drop_ratio=0.1)
```

### 6.2 混合检索调用

```python
from pymilvus import MilvusClient, AnnSearchRequest, WeightedRanker

def hybrid_search(client, dense_vec, sparse_vec, top_k=20):
    dense_req = AnnSearchRequest(
        data=[dense_vec], anns_field="dense",
        param={"metric_type": "COSINE", "params": {"ef": 128}},
        limit=top_k,
    )
    sparse_req = AnnSearchRequest(
        data=[sparse_vec], anns_field="sparse",
        param={"metric_type": "IP", "params": {}},
        limit=top_k,
    )
    ranker = WeightedRanker(0.8, 0.2)            # dense 0.8 / sparse 0.2
    return client.hybrid_search(
        collection_name="rag_kb_chunks",
        reqs=[dense_req, sparse_req],
        ranker=ranker,
        limit=top_k,
        output_fields=["text", "doc_name", "file_dir", "chunk_idx", "metadata"],
    )
```

**注意(Milvus 语义陷阱,实测为准)**: 单路 dense COSINE 检索返回**距离**,越小越相关;但本模块 `hybrid_search()` 经 `WeightedRanker` 融合后返回的字段实为**相似度**,越大越相关 —— 模块已把它直接暴露为 `score`,下游按 score 降序,**不要做 `1 - x` 反转或取负**(设计初期曾按距离语义写反,实测修正)。

### 6.3 入库

```python
def insert_chunks(client, chunks):
    # chunks: List[{"text", "dense": List[float], "sparse": Dict[int,float], ...}]
    entities = [
        {
            "text":      c["text"],
            "dense":     c["dense"],
            "sparse":    c["sparse"],
            "doc_name":  c["doc_name"],
            "file_dir":  c["file_dir"],
            "chunk_idx": c["chunk_idx"],
            "metadata":  c["metadata"],
        }
        for c in chunks
    ]
    client.insert(collection_name="rag_kb_chunks", data=entities)
```

## 7. RRF 倒数排名融合(`nodes/rrf_fuse.py`)

```python
RRF_K = 60
RRF_WEIGHTS = {"embedding": 1.0, "hyde": 1.0, "web": 1.0}  # 各路等权

def rrf_fuse(paths: Dict[str, List[Dict]]) -> List[Dict]:
    """paths: {"embedding": [...], "hyde": [...], "web": [...]},每路按 score 降序入参"""
    scores: Dict[str, float] = {}     # key=doc_id(=text hash 或 Milvus id)
    docs:   Dict[str, Dict] = {}
    for path, items in paths.items():
        w = RRF_WEIGHTS.get(path, 1.0)
        for rank, item in enumerate(items, start=1):
            doc_id = item.get("id") or hashlib.md5(item["text"].encode()).hexdigest()
            scores[doc_id] = scores.get(doc_id, 0.0) + w / (RRF_K + rank)
            if doc_id not in docs:
                docs[doc_id] = item
    fused = sorted(docs.values(), key=lambda d: scores[d.get("id") or hashlib.md5(d["text"].encode()).hexdigest()], reverse=True)
    return fused
```

## 8. 断崖检测重排(`nodes/cliff_rerank.py`)

### 8.1 输入与输出

- 输入:`rrf_chunks` + `original_query`
- 输出:`reranked_docs`(已动态截断)

### 8.2 算法伪代码

```python
# 重排得分 = BGE-reranker 0-1 score(DashScope / BGE-reranker-v2-m3)
# 算法:绝对阈值 + 相对阈值,任意一个触发就截断到当前 rank-1
# 边界:截断后 TopK 必须在 [RERANK_MIN_TOPK, RERANK_MAX_TOPK] 之间
def cliff_rerank(query, chunks,
                 gap_abs: float, gap_ratio: float,
                 min_topk: int, max_topk: int) -> List[Dict]:
    if not chunks:
        return []
    scored = sorted(rerank(query, chunks), key=lambda c: c["score"], reverse=True)
    n = len(scored)
    cut = n
    for i in range(1, n):
        prev, cur = scored[i - 1]["score"], scored[i]["score"]
        gap = prev - cur
        if gap >= gap_abs:                               # 绝对阈值
            cut = i
            break
        if prev > 0 and (gap / prev) >= gap_ratio:       # 相对阈值
            cut = i
            break
    cut = max(min_topk, min(cut, max_topk))               # 边界收敛
    return scored[:cut]
```

### 8.3 默认值(`.env`)

```
RERANK_GAP_ABS=1.0        # 绝对落差(0-1 标度)
RERANK_GAP_RATIO=0.3      # 相对落差
RERANK_MIN_TOPK=3
RERANK_MAX_TOPK=10
```

## 9. MinIO 对象存储(`app/core/minio_client.py`)

### 9.1 桶初始化

```python
def ensure_bucket(client: Minio, bucket: str):
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"AWS": ["*"]},
            "Action": ["s3:GetObject"],
            "Resource": [f"arn:aws:s3:::{bucket}/*"],
        }],
    })
    client.set_bucket_policy(bucket, policy)             # public-read
```

### 9.2 对象前缀命名

```
原文件:    uploads/<name>
转换产物:  converted/<stem>/<stem>.md
          converted/<stem>/images/<file>.jpg
          converted/<stem>/<other_assets>/...
```

注意:**无 `/auto/` 层级**(设计稿曾写 `converted/<stem>/auto/`,实现时去掉,与前端 `/converted/<stem>/...` URL 契约一致)。

### 9.3 后端代理路由(`app/api/converted.py`)

```python
@router.get("/converted/{stem:path}")
async def converted_proxy(stem: str):
    """把 /converted/<stem>/... 的请求流式代理到 MinIO。
    URL 契约与原本地 static mount 完全一致,前端零改动。
    """
    obj_path = f"converted/{stem}"
    resp = minio.get_object(Config.MINIO_BUCKET, obj_path)
    return StreamingResponse(
        _stream_minio(resp),
        media_type=_guess_mime(obj_path),
    )
```

`main.py` 移除 `app.mount("/converted", StaticFiles(...))`,改为 `app.include_router(converted_router)`。

## 10. MCP 自建服务(`mcp_server/server.py`)

### 10.1 server 端(mcp SDK 2.x)

```python
# ⚠️ 按 mcp SDK 2.x API 编写:v1 的 Server + @server.list_tools() 装饰器已移除
from mcp.server.mcpserver import MCPServer

server = MCPServer("rag-web-search")

@server.tool()   # schema 由函数签名类型注解自动生成
def web_search(query: str, count: int = 5) -> str:
    r = httpx.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": count},
        headers={"X-Subscription-Token": os.environ["BRAVE_SEARCH_API_KEY"]},
    )
    return _format_brave(r.json())   # [{title, url, snippet}] JSON 字符串,SDK 包成 TextContent
```

启动:`mcp_server/__main__.py` 用 stdio 传输拉起(进程内,不开端口);缺 `BRAVE_SEARCH_API_KEY` 时返回提示性 JSON,不抛未捕获异常。

### 10.2 client 端(`app/core/mcp_client.py` + 查询节点)

```python
# 进程内连接:stdio 传输,不开 HTTP
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def web_search(query: str, count: int = 5) -> List[Dict]:
    params = StdioServerParameters(command="python",
                                    args=["-m", "mcp_server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            res = await s.call_tool("web_search",
                                    {"query": query, "count": count})
            return _parse(res)
```

> **为什么用 stdio 而不是 HTTP**:与 LangGraph 节点同一进程内拉起,避免再起一个端口/进程,简化部署。

## 11. HyDE 触发策略(`nodes/preprocess.py` + `nodes/hyde_search.py`)

```
+----------------------+   启用 hyde   +-------------------+
| intent in {factual,  |-------------->| hyde_search        |
| explanatory}         |               | LLM 生成假设答案    |
|                      |               | 拼接到 rewritten 后 |
|                      |               | 走 hybrid_search    |
+----------------------+               +-------------------+
| intent in {chitchat, |   跳过 hyde
| creative}            |---(不加入图边)
+----------------------+
```

拼接模板:`combined_query = rewritten_query + " " + hyde_doc`,再走与 `embedding_search` 完全相同的 `hybrid_search()`。这样不需要独立的 HyDE 索引,只是同一集合上的二次检索。

## 12. 入库/查询图装配总览

```python
# app/rag/ingest_graph.py
ingest_wf = StateGraph(ImportGraphState)
ingest_wf.add_node("entry",                 NodeEntry())
ingest_wf.add_node("pdf_to_md",             NodePdfToMd())
ingest_wf.add_node("md_img",                NodeMdImg())
ingest_wf.add_node("doc_split",             NodeDocSplit())
ingest_wf.add_node("item_name_recognition", NodeItemNameRecognition())
ingest_wf.add_node("bge_embedding",         NodeBgeEmbedding())
ingest_wf.add_node("import_milvus",         NodeImportMilvus())
ingest_wf.set_entry_point("entry")
ingest_wf.add_edge("entry", "pdf_to_md")
ingest_wf.add_edge("pdf_to_md", "md_img")
ingest_wf.add_edge("md_img", "doc_split")
ingest_wf.add_edge("doc_split", "item_name_recognition")
ingest_wf.add_edge("item_name_recognition", "bge_embedding")
ingest_wf.add_edge("bge_embedding", "import_milvus")
ingest_wf.add_edge("import_milvus", END)
INGEST_GRAPH = ingest_wf.compile()

# app/rag/query_graph.py
query_wf = StateGraph(QueryGraphState)
# ... 节点注册、conditional_edges、汇聚到 rrf_fuse ...
QUERY_GRAPH = query_wf.compile()

# app/rag/pipeline.py — 薄壳
async def query(question, history, session_id=0, message_id=0) -> dict:
    # QUERY_GRAPH 整图一次跑完,返回 {answer, sources, meta}
    ...

def query_stream(question, history, session_id=0, message_id=0) -> Iterator[tuple[str, object]]:
    # 同步生成器,两段实现:
    # 1) 检索子图 RETRIEVAL_GRAPH.astream(stream_mode="updates"):节点完成即 yield
    #    ("status", 阶段文案),子图终态由各节点增量按序 merge 得到(state 无 reducer
    #    通道,merge 与 ainvoke 终态一致);后台线程 asyncio.run + queue 桥接回同步生成器
    # 2) 图外 LLMClient.stream_chat + ThinkStreamFilter 逐块 yield ("delta", 增量),
    #    结束 yield ("done", 完整答案) —— llama-index LLM 不发 LangChain 事件,
    #    astream_events 拿不到 token 级增量,generate 节点只服务非流式路径
    ...
```

## 13. 与现有模块的关系

| 现有模块 | 处置 | 说明 |
|----------|------|------|
| `app/core/llm.py` | **保留** | LangGraph 节点内直接用 `LLMClient` |
| `app/core/db.py` | **保留** | MySQL 历史、任务状态不变 |
| `app/core/embedding.py` | **废弃** | embo-01 / embedding-3 双供应商改由 `bge_embedding.py` 替换 |
| `app/core/milvus_client.py` | **废弃** | llama-index MilvusVectorStore 包装改直调 `milvus_hybrid.py` |
| `app/rag/pipeline.py` | **改写** | 变为 LangGraph 薄壳 |
| `app/rag/post.py` | **改写** | 改名为 `cliff_rerank` 节点,断崖算法搬进来 |
| `app/rag/retriever.py` | **废弃** | 检索逻辑搬到 `embedding_search` / `hyde_search` 节点 |
| `app/api/upload.py` | **改写** | 走 MinIO(原文件 + 转换产物落桶) |
| `main.py` | **修改** | 移除 `/converted` static mount,挂代理路由 |
| `static/index.html` | **不改** | `/converted/<stem>/images/<file>` URL 契约保留 |

## 14. 验证路径(手动)

1. `conda run -n rag uvicorn main:app --host 127.0.0.1 --port 8011 --reload`
2. `curl -F files=@x.pdf /upload/files` → 触发入库图,看 `import_milvus` 完成日志
3. `minio mc ls rag-kb/converted/<stem>/` → 确认 md + images 落桶
4. `curl -X POST /chat/stream -d '{...}'` → 触发查询图,观察 preprocess → 三路召回 → rrf_fuse → cliff_rerank → generate 日志
5. 浏览器打开 `http://127.0.0.1:8011/static/index.html` 提问,前端展示引用图(URL 走 `/converted/...` 代理路由,确认代理可流式回放图片)
6. `DELETE /upload/files/<name>` → 确认 Milvus 中该文件全部 chunk 清空 + MinIO 中 `uploads/<name>` 与 `converted/<stem>/` 两组对象都清空

## 15. 已知边界与后续

- **HyDE 假设文档**依赖 LLM 质量,实测若 LLM 本身不稳,该路召回可能拖低 RRF 排序,可通过 `Config.HYDE_ENABLED=False` 一键关闭。
- **web 搜索**结果作为参考来源,但 web 文档不入 Milvus,只在本次回答的 `sources` 数组里出现一次,不入历史。
- **重排模型**为本地 `sentence_transformers.CrossEncoder`(BGE-reranker-v2-m3,`RERANK_MODEL` 可换本地路径),推理异常时降级 RRF 分;曾规划的 `RERANK_BACKEND` 云端开关未实现,如需云端后端再立项。
- **慢模型延迟**:agnes 等模型单次调用有 10-40s"思考"延迟,闲聊/生成首字可能偏慢,属模型侧;检索阶段的等待已由 SSE `status` 阶段事件缓解(见 `chat-streaming` 规格 delta)。
- **MCP server** 仅承载 web 搜索一个工具;后续若增加数据库 / Slack / Jira 等工具,只需在 `mcp_server/server.py` 多 `@server.list_tools` 一项,LangGraph 节点不需改动。
