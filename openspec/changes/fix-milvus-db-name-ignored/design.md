# Design:修复 MilvusVectorStore 静默忽略 `db_name`

## 上下文

`pymilvus.MilvusClient` 和 `llama_index.vector_stores.milvus.MilvusVectorStore` 是**两条不同的接入路径**:

- `MilvusClient(uri=..., db_name=...)`:完整 pymilvus API,支持 `db_name` 隔离
- `MilvusVectorStore`:llama-index 的薄封装,内部走 `connections.connect(uri=...)`,**不接受也不传播 db_name**

代码里 `MilvusStore.vector_store` 用的是后者,所以无论 `Config.MILVUS_DB` 写什么,数据都落到 default DB。

这是 llama-index 库的限制(查看 `llama_index/vector_stores/milvus/base.py` 的 `MilvusVectorStore.__init__` 确认无 `db_name` 参数)。修这个 bug 等于绕开 llama-index 的便利层。

## 决策

### Path A vs Path B 二选一

**Path A(推荐,语义更清晰)**:

- 直接用 `MilvusClient` 管存储
- 代价:丢 `VectorStoreIndex` / `load_existing_index()` 的便利,要自己维护"id → text → source"的本地映射或反查 Milvus
- 收益:`MILVUS_DB` 真正生效,多租户 / 多环境隔离成真

**Path B(简单,务实)**:

- 删 `MILVUS_DB`,承认 single-DB 是当前现实
- 代价:失去 Milvus 已支持的 db_name 能力(虽然本仓库暂未用上)
- 收益:改动最小,代码清晰,新人不会被"配了不生效的配置"误导

**默认推荐 Path A**,因为:

1. `MilvusClient` 已经在用了(`_ensure_database()` 调用),完全绕开它反而更怪
2. llama-index 的 `VectorStoreIndex` 抽象对本仓库这个简单场景价值不大
3. 多 db 隔离是 Milvus 的强项之一,顺手启用符合预期

但 Path A 的工作量明显更大 — 实施前要在 proposal.md 顶部加 `## Chosen Path: A|B` 段拍板。

### 不等上游修复

llama-index 上游若要支持 `db_name` on `MilvusVectorStore`,需要 PR 走流程。本仓库**不等**,原因:

- 业务不阻塞
- 提 PR 后还得等版本发布 + 锁版本升级
- 自接管更可控

如果未来 llama-index 修了这个问题,本 change 可以反向 archive,重新接回 `MilvusVectorStore`。

### 不引入新依赖

修复不引入新 Python 包(`pymilvus` 已经在 requirements 里)。

## 验证挂钩

本 change archive 前必须验证:

1. (Path A)**回归**:`data/sample_kb.md` 入库 + 提问链路仍然可用
2. (Path A)**隔离**:用 `pymilvus.connections.connect(uri); utility.list_database()` 确认 collection 在 `rag_kb` 而非 `default`
3. (Path B)**清理**:`grep -r MILVUS_DB` 在仓库内(除归档注释外)零结果
4. **注释清理**:`git diff app/core/milvus_client.py` 不再包含"does not support switching DB"这类自相矛盾的描述

## 显式非设计

- **不引入**多 db 切换的运行期 API(用户重启时改 `.env` 即可)
- **不实现** db 备份 / 迁移工具(Milvus 自身工具负责)
- **不改** schema(向量字段 1536 维、`source` 是 VARCHAR 1024)