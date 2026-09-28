# hybrid-retrieval

> 从 OpenSpec 变更 `enterprise-rag-upgrade` 同步而来。

## Purpose

把现有的纯 dense 检索改造为「稠密向量 + 稀疏向量」双路混合检索:稠密由本地 BGE-M3 产出 1024 维向量,稀疏由同一模型产出的 learned sparse(BGE-M3 lexical weights),Milvus `hybrid_search()` 在库内用 `WeightedRanker(0.8, 0.2)` 融合两路,统一接口供查询图的 `embedding_search` 与 `hyde_search` 节点调用。

## Requirements

### Requirement: BGE-M3 本地嵌入

系统 SHALL 在 `app/core/bge_embedding.py` 提供 `BGEEmbedding(BaseEmbedding)`,通过 `FlagEmbedding.BGEM3FlagModel` 加载 `BAAI/bge-m3`(路径由 `Config.BGE_M3_MODEL`,设备由 `Config.BGE_M3_DEVICE`),实现 `_get_query_embedding / _get_text_embedding / _get_text_embeddings` 三处供 llama-index 路径使用,并额外暴露 `encode_sparse(text) -> Dict[int, float]` 方法供 Milvus hybrid search 直接取稀疏向量。

#### Scenario: dense 维度 1024
- **WHEN** `BGEEmbedding._get_text_embedding("hello")` 被调用
- **THEN** 返回长度为 1024 的 `list[float]`

#### Scenario: 稀疏向量为 CSR 字典
- **WHEN** `BGEEmbedding.encode_sparse("hello world")` 被调用
- **THEN** 返回 `Dict[int, float]`,键为 token id、值为权重,非空

#### Scenario: 本地推理
- **WHEN** 应用启动加载 `BGEEmbedding`
- **THEN** 不向任何外部 embedding 服务发起请求(网络层断网状态下也能产出向量)

### Requirement: Milvus collection schema

系统 SHALL 在 `app/core/milvus_hybrid.py` 中显式创建 collection `rag_kb_chunks`,字段:`id INT64 PK auto`、`text VARCHAR(4096)`、`dense FLOAT_VECTOR(1024)`、`sparse SPARSE_FLOAT_VECTOR`、`doc_name VARCHAR(256)`、`file_dir VARCHAR(512)`、`chunk_idx INT64`、`metadata JSON`;dense 走 HNSW 索引 `metric_type=COSINE`,sparse 走 SPARSE_INVERTED_INDEX `metric_type=IP`。

#### Scenario: 显式 schema 创建
- **WHEN** 首次启动且 collection 不存在
- **THEN** 自动 `create_collection` + `create_index`("dense" 与 "sparse"),`has_collection` 返回 true

#### Scenario: 索引自愈
- **WHEN** collection 已存在且 schema 正确,但 dense 或 sparse 向量索引缺失(Milvus streaming node 下可能发生)
- **THEN** 启动钩子检测 `list_indexes` 后自动补建缺失索引并 `load_collection`,无需人工 `/upload/clear` 重建

#### Scenario: 旧 collection 不兼容
- **WHEN** 检测到旧 collection 仅有 `dense` 单字段(无 `sparse` 字段)
- **THEN** 启动失败或主动 `drop_collection` 重建(由 `Config.AUTO_REBUILD_SCHEMA` 控制,默认 true)

### Requirement: 入库写入双向量

系统 SHALL 由入库图 `import_milvus` 节点把每个 chunk 的 dense(1024 维 float list)与 sparse(`Dict[int, float]`)**同时**写入 Milvus,通过 `MilvusClient.insert(collection_name="rag_kb_chunks", data=[...])`;任一向量为空的 chunk SHALL 被跳过并打日志,不入库。

#### Scenario: 双向量同写
- **WHEN** 一个 chunk 经 `bge_embedding` 节点产出
- **THEN** `import_milvus` 节点把 `{dense, sparse, text, doc_name, file_dir, chunk_idx, metadata}` 一并 insert

#### Scenario: 空向量跳过
- **WHEN** `dense` 或 `sparse` 任一为空
- **THEN** 跳过该 chunk,日志包含 `skip chunk idx=<n> due to empty vector`,Milvus 不写入

### Requirement: hybrid_search 调用封装

系统 SHALL 由 `app/core/milvus_hybrid.py` 暴露 `hybrid_search(dense_vec, sparse_vec, top_k=20, filters=None) -> List[Hit]`,内部构造两个 `AnnSearchRequest`(dense COSINE / sparse IP,各自 `limit=top_k`),用 `WeightedRanker(0.8, 0.2)` 融合,`MilvusClient.hybrid_search(...)` 返回 `output_fields=["text", "doc_name", "file_dir", "chunk_idx", "metadata"]`。

#### Scenario: 库内加权融合
- **WHEN** `hybrid_search([dense_vec], [sparse_vec], top_k=20)` 被调用
- **THEN** 返回最多 20 条 hit,每条 hit 携带 `text / doc_name / file_dir / chunk_idx / metadata`,排序由 `WeightedRanker` 决定

#### Scenario: top_k 边界
- **WHEN** 集合总数 < top_k
- **THEN** 返回结果数 = 集合总数,无越界

### Requirement: 分数语义警示

系统 SHALL 在 `app/core/milvus_hybrid.py` 的模块头注释里写清两套分数语义,防止下游用反:

- 单路 dense COSINE 检索返回的是**距离**,越小越相关(与相似度语义相反);
- 本模块 `hybrid_search()`(WeightedRanker 库内融合)返回的字段实为归一化后的**相似度**,越大越相关 —— 已直接以 `score` 暴露,下游节点按 score 降序即可,**不要做 `1 - x` 反转或取负**(实测 WeightedRanker 输出方向与单路距离相反,曾有按距离语义处理的错误论述,以此为准)。

#### Scenario: 头注释存在
- **WHEN** 阅读 `app/core/milvus_hybrid.py` 顶部 docstring
- **THEN** 同时写明 "COSINE 距离越小越相关(单路)" 与 "hybrid_search score 越大越相关",并明确不要反转

### Requirement: 接入查询图节点

系统 SHALL 由 `embedding_search` 与 `hyde_search` 两个节点**共享**调用 `hybrid_search`,区别仅在传入的 query 文本(`rewritten_query` vs `rewritten_query + " " + hyde_doc`),其他参数(权重、top_k、过滤)一致。

#### Scenario: 共用入口
- **WHEN** 任意节点调用 `milvus_hybrid.hybrid_search(...)`
- **THEN** 走同一函数,无重复实现

#### Scenario: HyDE 拼接
- **WHEN** `hyde_search` 节点构造查询文本
- **THEN** `combined = rewritten_query + " " + hyde_doc`,再走 `hybrid_search`;**不为 HyDE 单独建索引**
