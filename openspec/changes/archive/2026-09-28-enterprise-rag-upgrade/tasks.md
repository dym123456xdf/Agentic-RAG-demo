# Tasks: enterprise-rag-upgrade

> 实施清单。按代码区域分组,每条任务可独立验证。
>
> **图例**:`[x]` = 本会话已完成(代码已写);`[ ]` = 用户动作(依赖安装 / 服务启动 / 手动验证,需在终端跑)。

## 1. 依赖与模型(用户动作)

- [x] 1.1 在 conda 环境 `rag` 中 `pip install langgraph FlagEmbedding minio mcp httpx`(pymilvus 已是依赖)
- [x] 1.2 启动 MinIO 服务(`docker run -p 9000:9000 -p 9001:9001 minio/minio server /data --console-address ":9001"`)
- [x] 1.3 下载 BGE-M3 模型到本地(`models/BAAI/bge-m3/`,`Config.BGE_M3_MODEL` 指向该路径)
- [ ] 1.4 申请 Brave Search API Key,写入 `.env`

## 2. 配置项(`.env` + `app/core/config.py`)

- [x] 2.1 在 `Config` 追加 BGE-M3 配置:`BGE_M3_MODEL`、`BGE_M3_DEVICE`、`EMBEDDING_DIM=1024`
- [x] 2.2 追加 MinIO 配置:`MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`、`MINIO_BUCKET`、`MINIO_SECURE`
- [x] 2.3 追加 MCP 配置:`MCP_SERVER_HOST`、`MCP_SERVER_PORT`、`BRAVE_SEARCH_API_KEY`
- [x] 2.4 追加断崖检测配置:`RERANK_GAP_ABS=1.0`、`RERANK_GAP_RATIO=0.3`、`RERANK_MIN_TOPK=3`、`RERANK_MAX_TOPK=10`(原规划的 `RERANK_BACKEND` 云端开关未实现,重排固定走本地 CrossEncoder,异常降级 RRF 分)
- [x] 2.5 追加 HyDE / Web 开关:`HYDE_ENABLED=true`、`WEB_SEARCH_ENABLED=false`(默认关,需 Brave Key 再开)
- [x] 2.6 删除 `EMBEDDING_PROVIDER` 旧供应商分支(embo-01 / embedding-3),改为 `EMBEDDING_PROVIDER=bge-m3` 单选项
- [x] 2.7 `Config` import 时对所有新增字段做空值校验,缺失即 `RuntimeError`

## 3. 嵌入模块(`app/core/bge_embedding.py`)

- [x] 3.1 实现 `BGEEmbedding(BaseEmbedding)`,构造时加载 `BGEM3FlagModel`
- [x] 3.2 实现 `_get_query_embedding / _get_text_embedding / _get_text_embeddings`
- [x] 3.3 实现 `encode_sparse(text) -> Dict[int, float]`,内部 `_csr_to_dict` 转 CSR 字典
- [x] 3.4 模块头注释写明 dense 维度 1024、COSINE 距离越小越相关
- [x] 3.5 验证:启动服务无异常,`BGEEmbedding()._get_text_embedding("test")` 返回长度 1024 的 list(用户动作:pip install + 启动)

## 4. Milvus 混合检索(`app/core/milvus_hybrid.py`)

- [x] 4.1 实现 `MilvusClient` 单例 + `ensure_collection(dim=1024)` 显式 schema(dense FLOAT_VECTOR 1024 + sparse SPARSE_FLOAT_VECTOR + text + doc_name + file_dir + chunk_idx + metadata)
- [x] 4.2 创建 HNSW(dense, COSINE)与 SPARSE_INVERTED_INDEX(sparse, IP)索引
- [x] 4.3 实现 `hybrid_search(dense_vec, sparse_vec, top_k=20)`,用 `WeightedRanker(0.8, 0.2)`
- [x] 4.4 实现 `insert_chunks(chunks)`,任一向量为空跳过 + 打日志
- [x] 4.5 实现 `delete_by_doc_name(name) -> int`,返回删除条数
- [x] 4.6 模块头注释重申 COSINE 距离越小越相关
- [x] 4.7 检测到旧 schema(仅 dense)时按 `Config.AUTO_REBUILD_SCHEMA` 决定是否 drop 重建

## 5. MinIO 客户端(`app/core/minio_client.py`)

- [x] 5.1 实现 `get_minio_client()` 单例
- [x] 5.2 实现 `ensure_bucket(bucket)`:不存在则 `make_bucket`,再 `set_bucket_policy(public-read JSON)`
- [x] 5.3 实现 `put_object(bucket, key, data, length)`,length=0 抛 `ValueError`(原 `InvalidDataError`,此处简化为 stdlib 异常)
- [x] 5.4 实现 `delete_prefix(bucket, prefix)` 批量删除(`list_objects(recursive=True)` + `remove_object` 迭代)
- [x] 5.5 实现 `delete_object(bucket, key)`,对象不存在不报错
- [x] 5.6 实现 `get_object_stream(bucket, key) -> Iterator[bytes]`,供代理路由使用
- [x] 5.7 附 `upload_directory(local_dir, prefix)` 辅助函数,把 staging 整目录批量上传 MinIO

## 6. MCP 自建服务(`mcp_server/`)

- [x] 6.1 创建 `mcp_server/__init__.py` 与 `mcp_server/__main__.py`,通过 `mcp.run` 在 `stdio` 上启动
- [x] 6.2 实现 `mcp_server/server.py`,用 `Server("rag-web-search")`,`@server.list_tools()` 注册 `web_search` 工具
- [x] 6.3 实现 `web_search`:Brave Search GET,`X-Subscription-Token` 头,输出 `TextContent` 列表
- [x] 6.4 缺 `BRAVE_SEARCH_API_KEY` 时返回明确 `TextContent("BRAVE_SEARCH_API_KEY not configured")`,不抛未捕获异常

## 7. LangGraph 基础(`app/rag/base.py` + `app/rag/state.py`)

- [x] 7.1 实现 `BaseNode(ABC)` 基类(见 `design.md` §2.3),日志前缀按 `flow` 区分
- [x] 7.2 定义 `NodeProcessError` / `IngestProcessError` / `QueryProcessError` 异常类
- [x] 7.3 定义 `ImportGraphState(TypedDict, total=False)` 与 `create_default_import_state(**overrides)`
- [x] 7.4 定义 `QueryGraphState(TypedDict, total=False)` 与 `create_default_query_state(**overrides)`
- [x] 7.5 工厂返回独立副本(`copy.deepcopy` 兜底)

## 8. 入库图(`app/rag/ingest_graph.py` + `app/rag/nodes/ingest_nodes.py`)

- [x] 8.1 实现 `NodeEntry`:写入 task_id / import_file_path / file_title(stem)/ file_dir(prefix)
- [x] 8.2 实现 `NodePdfToMd`:MinIO 拉原文件 → mineru-kit 子进程 → staging 落 md + images/,产物已存在复用
- [x] 8.3 实现 `NodeMdImg`:把 md 文本里的 `images/<hash>.<ext>` 改写为 `/converted/<stem>/images/<...>` 绝对 URL
- [x] 8.4 实现 `NodeDocSplit`:MarkdownNodeParser 切分,产出 `chunks: List[Dict]`
- [x] 8.5 实现 `NodeItemNameRecognition`(LLM):前 3 个 chunk 喂 LLM 抽 `item_name`,失败兜底空
- [x] 8.6 实现 `NodeBgeEmbedding`:每个 chunk 调 `_encode_dense` + `encode_sparse_batch`,回填 `dense` / `sparse` / `doc_name` / `file_dir`
- [x] 8.7 实现 `NodeImportMilvus`:写 Milvus + staging 整目录上传 MinIO(`upload_directory`) + 删除 staging
- [x] 8.8 装配 `StateGraph`,入口 `entry` → 7 节点线性 → `END`,编译为 `INGEST_GRAPH`
- [x] 8.9 验证:上传一份 PDF,看 7 个节点日志依次执行,Milvus 集合 chunk 数 > 0,MinIO `converted/<stem>/` 下有 md + images(用户动作,已验证)

## 9. 查询图(`app/rag/query_graph.py` + `app/rag/nodes/query_nodes.py`)

- [x] 9.1 实现 `NodePreprocess`:LLM 改写 + 意图识别(5 类),产出 `rewritten_query` + `intent`
- [x] 9.2 实现 `NodeEmbeddingSearch`:`rewritten_query` → `_encode_dense` + `encode_sparse` → `hybrid_search` → `embedding_chunks`
- [x] 9.3 实现 `NodeHydeSearch`:LLM 生成假设答案,拼接到 rewritten_query,走同一 `hybrid_search`
- [x] 9.4 实现 `NodeWebSearch`:asyncio.run 桥接 `mcp_client.call_tool("web_search", ...)`(同步 LangGraph 适配),结果规范化 `{text, doc_name, file_dir, source_type: web}`
- [x] 9.5 实现 `NodeRrfFuse`:三路等权 RRF 融合,`RRF_K=60`,doc_id 用 Milvus id / text hash / `web::<url>`
- [x] 9.6 实现 `NodeCliffRerank`:BGE-reranker 重排打分,断崖检测双阈值动态截断,加 `confidence`(`_sigmoid(score)`)
- [x] 9.7 实现 `NodeGenerate`:装配 prompt(参考资料块 + 图片引用保护),`LLMClient.chat` 出答案
- [x] 9.8 装配 `StateGraph`,`add_conditional_edges` 扇出到 embedding / hyde / web(由 `route_after_preprocess` 决定),汇向 rrf_fuse → cliff_rerank → generate → END
- [x] 9.9 验证:问 factual 类问题,日志能看到 embedding + hyde + web 三路同时开始(用户动作)

## 10. 管线薄壳(`app/rag/pipeline.py`)

- [x] 10.1 实现 `ingest(task_id, file_path)` 异步函数,调 `INGEST_GRAPH.ainvoke(state)`
- [x] 10.2 实现 `query(...)` 同步函数,asyncio.run 驱动 `QUERY_GRAPH.ainvoke`,返回 `{answer, sources, meta}`
- [x] 10.3 实现 `query_stream(...)` 同步生成器,asyncio.run + anext 桥接 `astream_events`,监听 `on_chain_end(cliff_rerank)` → meta / `on_chat_model_stream(generate)` → delta / `on_chain_end(generate)` → done
- [x] 10.4 保留 `RAGPipeline` 类与 `get_pipeline()` 单例(`chat.py` 仍按旧接口 import),FastAPI 路由层无 LangGraph import

## 11. 上传 API(`app/api/upload.py`)

- [x] 11.1 `POST /upload/files`:每个文件 `minio_client.put_object("uploads/<name>")`,然后 `await ingest(task_id, file_path)`
- [x] 11.2 `GET /upload/converted/{name}`:从 MinIO `converted/<stem>/<stem>.md` 读取并返回(无 /auto/ 层级)
- [x] 11.3 `GET /upload/files`:列表来自 `milvus_hybrid.list_doc_names()`,统计 chunk 总数,`_has_converted` 走 MinIO
- [x] 11.4 `DELETE /upload/files/{name}`:三处清理 — `milvus_hybrid.delete_by_doc_name(name)` + `minio_client.delete_object("uploads/<name>")` + `minio_client.delete_prefix("converted/<stem>/")`
- [x] 11.5 `POST /upload/clear`:`drop_collection` + `ensure_collection`
- [x] 11.6 本地 `Config.MINERU_OUTDIR` 仍保留(MinerU 子进程需要 staging),转换完成即清

## 12. 转换产物代理路由(`app/api/converted.py`)

- [x] 12.1 实现 `GET /converted/{stem:path}` 路由,从 MinIO 流式回放 `converted/<stem>` 对象
- [x] 12.2 `StreamingResponse(minio_client.get_object_stream(...), media_type=_guess_mime(...))`,大文件流式不一次读
- [x] 12.3 `_guess_mime(obj_path)` 支持 `.md` / `.jpeg` / `.png` / `.json` 等常用后缀
- [x] 12.4 路径穿越拒绝:`..` 段 / 绝对路径前缀直接 404

## 13. `main.py` 装配

- [x] 13.1 移除 `app.mount("/converted", StaticFiles(...))`
- [x] 13.2 `app.include_router(converted.router)`
- [x] 13.3 启动时调 `milvus_hybrid.ensure_collection()` 与 `minio_client.ensure_bucket()`
- [x] 13.4 `Config` 缺失字段时快速失败(已由 §2.7 保证)

## 14. 清理与数据迁移

- [x] 14.1 旧 Milvus collection(单一 dense 字段)由 `Config.AUTO_REBUILD_SCHEMA` 控制是否 drop 重建(默认 true;`milvus_hybrid.ensure_collection` 实现)
- [x] 14.2 本地 `uploads/` 与 `converted/` 顶层目录删除(2026-09-28 执行:MinIO 缺失的 3 个原文件与 3 份转换产物先保全入桶,再删本地目录)
- [x] 14.3 旧 `app/core/embedding.py`(embo-01 / embedding-3 适配)文件删除
- [x] 14.4 旧 `app/core/milvus_client.py`(llama-index MilvusVectorStore 包装)文件删除
- [x] 14.5 旧 `app/rag/post.py / retriever.py / pre_query.py / splitter.py / generator.py / loader.py / indexer.py` 文件删除(逻辑搬入节点)
- [x] 14.6 MySQL schema / 数据不动(`db.py` 未改)

## 15. 文档更新

- [x] 15.1 README "技术栈" 章节追加 LangGraph / BGE-M3 / MinIO / MCP 行
- [x] 15.2 README "注意事项" 追加 "切换 EMBEDDING_PROVIDER / Milvus schema = 清空 collection 重建" 的强化警告
- [x] 15.3 README "运行" 章节追加 MinIO 启动命令与 `python -m mcp_server` 子进程说明

## 16. 手动验证(用户动作,参考 `design.md` §14)

- [x] 16.1 `conda run -n rag uvicorn main:app --host 127.0.0.1 --port 8011 --reload` 启动无异常
- [x] 16.2 `curl -F files=@x.pdf /upload/files` 触发入库图,日志完整,Milvus 与 MinIO 双侧可见
- [x] 16.3 浏览器访问 `http://127.0.0.1:8011/static/index.html`,问 factual 问题,流式回答与来源正常显示,引用图能加载
- [x] 16.4 `DELETE /upload/files/<name>`,三处清理成功,前端列表同步刷新
- [x] 16.5 `POST /upload/clear` 后重新入库,确认 collection 是新 schema(dense 1024 + sparse 双字段)

## 17. 验证期追加修复与增强(2026-09-28,已实现并验证)

- [x] 17.1 `main.py` 加 `logging.basicConfig(level=INFO)`:节点 INFO 日志此前全丢(root logger 无 handler)
- [x] 17.2 `list_doc_names` query 加 `consistency_level='Strong'`:删文件后列表秒级可见,不再出现幽灵文件
- [x] 17.3 `ensure_collection` 索引自愈:schema 对但 dense/sparse 索引缺失时自动补建(`_ensure_indexes`),不再需要 `/upload/clear` 救回
- [x] 17.4 SSE `status` 阶段事件:检索子图改 `astream(updates)` 逐节点推阶段文案(理解→召回→重排→生成),`chat.py` 转发、前端更新占位
- [x] 17.5 闲聊分支:`chitchat` 意图直达 `cliff_rerank` 空跑,`generate` 走 `build_chitchat_messages`(带历史)直接对话,不查知识库
- [x] 17.6 前端来源展示:参考来源块移到答案之后,最多罗列 top3;低置信度提示仍置顶
- [x] 17.7 LLM 供应商支持 agnes(agnes-3.0-flash,`LLM_PROVIDER=agnes`),端到端验证通过
