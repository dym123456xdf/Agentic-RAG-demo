# Proposal

## Why

首页单页把上传、文件管理、统计、聊天全部堆在一屏,信息密度过高;且问答历史只存在于前端内存,服务重启即丢失,无法回溯。需要一个独立管理页承载"重信息",并引入 MySQL 持久化问答历史、支持多会话管理;同时 MinerU 转换产物落盘后无处查看,需要人工核对转换质量的入口。

## What Changes

- 新增管理页 `static/manage.html`,双 tab:**文件管理**(拖拽上传、目录入库、已入库列表、统计)+ **问答历史**(按会话分组,每条可展开来源片段与意图/改写/召回 meta)
- 首页 `static/index.html` 瘦身:侧边栏改为 会话列表(新建/切换/删除)+ 管理页入口;上传/目录入库/文件列表/统计 UI 全部挪入管理页;**聊天区回答保持现状,照常显示来源与 meta**
- **BREAKING**:`POST /chat` 请求体从 `{question, history}` 改为 `{question, session_id}`;多轮改写所需的对话历史由后端从 MySQL 读取,前端不再传 `history`
- 新增 MySQL 持久化(Docker 新容器,独立于 milvus_demo compose):`sessions` + `messages` 两表,sources/meta 存 JSON 列;新增 `/sessions` CRUD 与按会话查消息接口
- 管理页支持查看 PDF/DOCX/PPTX 的 MinerU 转换产物:新增只读接口返回 `converted/` 下对应 `.md` 内容(防路径穿越);`GET /upload/files` 扩展"是否有转换产物"标志;`.md`/`.txt` 原生文本与 `MINERU_ENABLED=false` 时无产物、不显示入口
- `.env` 新增 `MYSQL_*` 配置项;共享样式抽为 `static/style.css`
- v1 会话能力:新建/列表/切换/删除,不做重命名;首页"清空对话"语义变为"清空当前会话消息"

## Capabilities

### New Capabilities

- `chat-sessions`:多会话聊天与历史持久化 —— MySQL 会话/消息存储,`/chat` 按 `session_id` 落库并由后端提供历史上下文,`/sessions` CRUD 与按会话查消息
- `manage-page`:管理页 —— 文件管理(上传/目录入库/列表/统计)、MinerU 转换产物人工核对查看、问答历史按会话回溯

### Modified Capabilities

(项目当前无既有 specs,均为新能力)

## Impact

- **后端**:`app/api/chat.py`(签名改造)、`app/api/upload.py`(文件列表扩展、新增转换产物只读接口)、新增会话/历史存储模块与 `/sessions` 路由、`app/rag/pipeline.py` 的 `query()` 改为按 `session_id` 自取历史、`app/core/config.py` 新增 `MYSQL_*` 配置
- **前端**:`static/index.html` 瘦身改造、新增 `static/manage.html`、抽取共享 `static/style.css`
- **依赖**:Python MySQL 驱动(PyMySQL)、Docker MySQL 容器(新服务,需数据卷持久化)、`.env` 新增 `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE`
- **兼容**:前端与后端需同步升级(`history` 参数移除为破坏性变更);Milvus 与既有入库数据不受影响
