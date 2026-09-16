# 修复 MilvusVectorStore 静默忽略 `db_name`

## Why

`app/core/config.py` 把 `MILVUS_DB=rag_kb` 当作必填配置项,但 `app/core/milvus_client.py` 实际构造流程是:

```python
self.client = pymilvus.MilvusClient(uri=MILVUS_URI, db_name=MILVUS_DB)   # 这一行 db_name 生效
...
self.vector_store = MilvusVectorStore(                                    # 这一行不传 db_name
    uri=..., dim=..., overwrite=False, ...
)
```

`llama_index.vector_stores.milvus.MilvusVectorStore` 内部走 `connections.connect(...)`,**忽略**外层 `MilvusClient` 的 `db_name`,数据实际写到 default DB(`"default"`)。

后果:

- `MILVUS_DB=rag_kb` 这个配置项**形同虚设** — 改它没用,数据永远在 default
- 用户误以为自己的数据在隔离的 `rag_kb` 库里(比如多租户场景),实际所有人共享 default,潜在数据泄露
- `.env` 模板里把 `MILVUS_DB` 列为"必填"会持续误导新用户

代码里那段注释也矛盾 — `MilvusClient` 显式传了 `db_name`,但同文件后面又说"MilvusVectorStore does not support switching DB" — 一边说支持,一边说不支持,后人接手会被绕晕。

## What Changes

让 `MILVUS_DB` 真正生效,或者显式承认它无效并从配置面去掉。

**两条路,实施时选一条**:

### Path A(推荐):绕开 llama-index,直接用 `MilvusClient` 管存储

把 `app/rag/indexer.py` 从 `VectorStoreIndex.from_documents(vector_store=...)` 改为手动循环:

1. 用 `embedding.embed_documents(texts)` 拿向量(已有 `BaseEmbedding` 适配器)
2. 用 `MilvusClient.insert(collection_name=..., data=[{...}])` 写入
3. 检索时反着来:`MilvusClient.search(...)` 拿 `(id, distance, entity)`,再到本地缓存或重新构造 Node

代价:丢掉 `VectorStoreIndex` 的便利(自动反序列化、Node 解析、`load_existing_index()`),需要自己重写。

### Path B(简单):承认无效,从 `.env` 和 `config.py` 移除 `MILVUS_DB`

如果短期不打算支持多库,直接把 `MILVUS_DB` 从配置面拿掉,代码注释里写一句"如需多库隔离请用多个 standalone 实例"。改动最小,但失去 `MilvusClient` 已支持的 db_name 能力。

**影响范围**:

- 修改:`app/core/milvus_client.py`(去掉误导注释)
- 修改:`app/rag/indexer.py`(按所选路径二选一)
- 修改:`app/core/config.py`(按所选路径 — Path A 加 `MILVUS_DB` 强调"已生效",Path B 直接移除)
- 修改:`CLAUDE.md`(§3 取舍段、§4 `.env` 段更新事实口径)
- 不动:检索查询路径(pipeline / retriever)— 它们都通过 `load_existing_index()` 间接拿到 store,跟着改

**新增能力**(记入 `specs/api-surface` 或新增 `specs/storage` 的 `## ADDED Requirements`):

- `MILVUS_DB` 配置要么真正生效,要么从配置面移除(由所选路径决定)

## Non-Goals

- **不修** llama-index 库本身(向上游提 issue 等不及)
- **不引入**多库管理 UI(本仓库是 demo)
- **不重构**整个 storage 层(只针对这一个具体失效)
- **不实现** Milvus 权限 / RBAC / 用户管理(Milvus 自身能力,本系统不集成)

## Out of Scope

- 选择 Milvus vs Qdrant vs Weaviate — 假设 Milvus 已是决策
- 切换到 Milvus 2.5+ 的新 API(等业务有真实需求时再做)

## Success Criteria

1. `MILVUS_DB=rag_kb` + `MILVUS_DB=other_db` 启动两个不同 service → 各自的数据**不会**混在一起(Path A),或者该配置被移除且 `.env` 模板不再列出(Path B)
2. 现有 `data/sample_kb.md` 的入库 + 检索路径在修复后**仍然可用**(回归)
3. `MilvusVectorStore` 在代码里要么不再使用,要么有明确的"不传 db_name 是预期行为"注释