# CLAUDE.md

## 项目简介

个人知识库 RAG 服务(企业版):上传 PDF / Markdown / Word / PPT 等文档,即可通过网页或 API 进行有据可查的问答 —— 答案只基于库内资料 + Web 检索补充,并附来源引用与置信度提示。单页前端在 `static/index.html`。

## 技术栈

- **后端框架**:FastAPI(入口 `main.py`,启动钩子保证 MinIO 桶 / Milvus collection 就绪)
- **编排**:LangGraph —— 入库 / 查询跑在 StateGraph 上,业务逻辑全在节点
- **检索**:Milvus 混合检索(dense + sparse,WeightedRanker 融合)+ BGE-M3 本地 embedding + BGE-reranker-v2-m3 断崖检测重排;搜索模式三选一互斥,RRF 模式内融合(细节见 `.claude/rules/retrieval.md`)
- **存储**:MinIO(原文件 + MinerU 转换产物)+ MySQL(问答历史,懒加载可降级)
- **MCP 双 transport**:① 自建 Brave Search 服务(stdio);② 外部 xiaohongshu-mcp(小红书搜索,Streamable HTTP,独立部署 + 扫码登录)
- **运行环境**:Python 3.13,conda 环境 `rag`;仓库没有 requirements.txt / pyproject.toml / tests —— 不存在,不要找

## 目录结构

```
main.py                  # FastAPI 入口:组装 app + 挂路由 + 启动钩子
app/
  api/                   # 路由层(薄):upload / chat / sessions / converted / config
  core/                  # 基础设施:config(.env 快速失败)/ llm / bge_embedding /
                         #   milvus_hybrid / minio_client / mcp_client / db(MySQL)
  rag/                   # LangGraph 编排:pipeline(薄壳)/ ingest_graph / query_graph /
                         #   state(状态契约)/ base(节点基类)/ nodes/(全部业务节点)
  proxy.py               # Anthropic→OpenAI 协议代理(给 Claude Code 自身用,与本服务运行时无关)
mcp_server/server.py     # 自建 MCP 服务:Brave Search web_search 工具
static/index.html        # 单页前端
.claude/rules/           # 模块级规则(paths 按文件按需加载,见文末)
openspec/                # OpenSpec 变更产物
blobs/                   # 内容寻址存储(哈希分桶,入库跟踪)
converted/               # 运行期产物(MinerU 转换 staging,已 gitignore,别手工改)
```

## 运行与验证

```bash
conda run -n rag uvicorn main:app --host 127.0.0.1 --port 8011 --reload
```

- 端口用 8011:8000 已被本机 Docker 占用。`.env` 里的 `PORT` 只影响启动日志打印,实际端口以 uvicorn 命令行为准。
- 验证手段就是启动服务、手动调 API(上传 → 提问;问答走 SSE 流式)。
- 服务起不来先查 `.env`:`app/core/config.py` 在 import 时读配置并快速失败,MinIO / Milvus / MCP / MySQL 任一关键项缺失都会直接报错。

## 代码规范

- 注释与 docstring 一律用中文。
- 业务逻辑只写在 LangGraph 节点(`app/rag/nodes/`);`pipeline.py` 是薄壳、API 层只做参数组装 —— 加功能先进图,别在路由里写逻辑。
- 各模块的坑(切分、metadata、重排语义等)写在各自文件的 docstring 头部 —— 动哪个模块,先读哪个文件头部注释。
- 变更走 OpenSpec 规范驱动:`/opsx:*` 命令(propose / apply / archive),产物在 `openspec/`。

## IMPORTANT — 硬约束

- `EMBEDDING_PROVIDER` 只支持 `bge-m3`(本地 BGE-M3),其它值启动即失败;换 embedding 模型 = 更换向量空间,必须清空 Milvus collection 全量重新入库。
- Milvus 分数有两套语义,别混:单路 dense COSINE search 返回「距离」越小越相关;`milvus_hybrid.hybrid_search()` 返回的 score 是 WeightedRanker 融合相似度,越大越相关(详见 `app/core/milvus_hybrid.py` 头部注释)。
- 入库按文件名幂等跳过(前端预检 + 后端 `doc_name` 命中两道防线):同名文件重传不入库、不重复消耗 embedding,改内容不会更新索引,但 MinIO 里的原文件仍会被覆盖。
- MySQL 问答历史懒加载:MySQL 不可用时问答照常、只是历史降级 —— 别把连不上 MySQL 当成服务故障。

## 模块级规则(`.claude/rules/`)

细节规则按主题拆在 `.claude/rules/`,frontmatter 用 `paths` 指定生效文件 —— 读到匹配文件时自动注入,不用全部常驻:

- `retrieval.md` —— 混合检索 / 断崖重排 / RRF 模式内融合 / 搜索模式互斥路由
- `xhs-mcp.md` —— Brave / 小红书 MCP 的部署、登录、降级语义与同账号互踢
- `storage.md` —— MinIO / MySQL / 入库幂等细节
