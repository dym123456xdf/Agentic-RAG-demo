# Tasks:修复 MilvusVectorStore 静默忽略 `db_name`

## 0. 在 Path A 和 Path B 之间拍板

- [ ] 0.1 在 proposal.md 顶部加 `## Chosen Path: A|B` 段,记录决策理由(本次 change 创建时已注明"实施时选一条",开工前必须拍板)
- [ ] 0.2 若选 Path A,补 §1(直接 MilvusClient 管理)+ §3(spec 写 storage 能力);若选 Path B,只做 §2(配置面清理)+ §3(spec 标注配置项移除)

## 1. (Path A) 重写 `app/rag/indexer.py` 直接用 `MilvusClient`

- [ ] 1.1 新增私有函数 `_ensure_collection_schema(client, collection_name, dim, has_source_scalar=True)`:
  - 检查 collection 是否存在,不存在则创建(`FieldSchema(..., is_primary=True)` + `FloatVectorField(dim)` + `VarCharField("source", max_length=512)`)
  - index params:`{"metric_type": "COSINE", "index_type": "IVF_FLAT", "params": {"nlist": 1024}}`(小数据集够用,数据多再换 HNSW)
- [ ] 1.2 重写 `build_from_path`:
  - 调用 `loader.load(path)` → `splitter.split(docs)`
  - 对每个 node:`embedding.embed_documents([node.text])` 拿向量
  - 构造 `{"id": node.doc_id, "vector": vec, "source": node.metadata["source"], "text": node.text}` 列表
  - `client.insert(collection_name, data)`
  - 保留 `list_sources()` 去重 + `flush()` 行为
- [ ] 1.3 新增 `query_by_vector(vector, top_k, cutoff)`:`client.search(collection_name, data=[vector], limit=top_k, output_fields=["source", "text"], search_params={"metric_type": "COSINE"})` → 返回 `[(node_like, distance)]`
- [ ] 1.4 把 `Retriever` 从 `load_existing_index()` + `index.as_retriever()` 改为:
  - 保留 `load_existing_index()` 作为占位(返回 `None` 或一个新对象)
  - 实际检索时:`embedding.embed_query(q)` → `query_by_vector(...)` → 手动构造 Node 列表
- [ ] 1.5 删掉 `app/core/milvus_client.py` 里误导性的"MilvusVectorStore does not support switching DB"注释;在 `MilvusStore.vector_store` 属性上加 `@property` deprecation warning(指向新的 `client` + `query_by_vector` 用法)

## 2. (Path B) 从配置面移除 `MILVUS_DB`

- [ ] 2.1 从 `app/core/config.py` 删除 `MILVUS_DB` 字段
- [ ] 2.2 `app/core/milvus_client.py` 构造 `MilvusClient` 时不再传 `db_name`
- [ ] 2.3 `CLAUDE.md` §4 `.env 必填项` 段去掉 `MILVUS_DB` 一行
- [ ] 2.4 在 `app/core/milvus_client.py` 顶部 docstring 加一段:"本系统使用 Milvus default DB;如需多环境隔离,部署多个 standalone 实例 + 不同 `MILVUS_URI`"
- [ ] 2.5 (可选)建 `.env.example` 列出当前真实生效的环境变量(本仓库目前没有)

## 3. Spec 更新

- [ ] 3.1 (Path A) 在 `openspec/changes/fix-milvus-db-name-ignored/specs/storage/spec.md` 写 `## ADDED Requirements`,新增:
  - `### Requirement: Per-database isolation honored`
  - `### Requirement: Direct MilvusClient writes`
- [ ] 3.2 (Path B) 不新建 spec,但在 `openspec/changes/fix-milvus-db-name-ignored/proposal.md` 的 "What Changes" 段明确写"MILVUS_DB 配置项被移除"
- [ ] 3.3 archive 时合并到 `openspec/specs/`

## 验证

- [ ] V.1 (Path A) 启动 service + 上传 sample_kb.md + 提问 → 检索仍然正常
- [ ] V.2 (Path A) 用 Milvus 客户端(`pymilvus.connections.connect(...) + utility.list_database()`)查 `rag_kb` 库,确认 collection 在该库而非 default
- [ ] V.3 (Path B) `grep -r MILVUS_DB app/ CLAUDE.md` 应**零结果**(除了可能的归档注释)
- [ ] V.4 `git diff app/core/milvus_client.py | grep -i 'does not support'` 应**零结果**(去掉误导注释)