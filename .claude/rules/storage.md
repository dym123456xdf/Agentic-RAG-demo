---
paths:
  - app/core/minio_client.py
  - app/core/db.py
  - app/api/upload.py
  - app/api/sessions.py
  - app/api/converted.py
  - app/rag/ingest_graph.py
  - app/rag/nodes/ingest_nodes.py
---

# 存储规则

## MinIO

- 存原文件 + MinerU 转换产物;启动钩子保证桶就绪
- 前端取文件的 URL 走后端代理路由(`app/api/converted.py`),不直连 MinIO
- `blobs/` 是内容寻址存储(哈希分桶,入库跟踪);`converted/` 是运行期 staging(已 gitignore,别手工改)

## MySQL(懒加载可降级)

- 只存问答历史(sessions 路由);MySQL 不可用时问答照常、只是历史降级 —— 别把连不上 MySQL 当成服务故障

## 入库幂等(IMPORTANT)

按文件名幂等跳过,两道防线:前端上传前预检 + 后端 `doc_name` 命中。

- 同名文件重传**不入库**、不重复消耗 embedding
- 改内容**不会更新索引**(同名即跳过)
- 但 MinIO 里的原文件**仍会被覆盖**
