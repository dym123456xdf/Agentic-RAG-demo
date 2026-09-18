# Design

## Context

现状(动机见 proposal.md):

- 后端完全无状态:多轮对话的 `history` 由前端内存维护,每次 `/chat` 传最近 6 条;服务重启历史即丢。
- `pipeline.query(question, history)` 不感知存储;`QueryPreProcessor._rewrite` 用最近 3 轮历史做指代改写。
- 唯一外部服务是 Milvus(docker compose 项目 `milvus_demo`,独立于本仓库)。
- `config.py` 采用 import 时快速失败模式(`_need`),新增必填配置应沿用此惯例。
- MinerU 通道已把 PDF/DOCX/PPTX 转换产物落盘 `converted/<原文件名>.md`(含原后缀),`converted_md_path()` 是唯一定位函数;但没有任何接口能读取产物内容。
- 前端为单文件 `static/index.html`(内联样式与脚本,原生 JS,无构建工具)。

## Goals / Non-Goals

**Goals:**

- 历史上下文单一数据源:服务端(MySQL)为唯一权威,前端不传 `history`
- 首页/管理页职责分离,首页聊天区展示逻辑不变
- 转换产物可人工核对,接口访问收敛在 `converted/` 目录内
- 新依赖最小化,沿用现有"快速失败 + 启动自建"惯例(参考 `milvus_client` 自动建库)

**Non-Goals:**

- 会话重命名、会话搜索
- 流式响应(SSE)
- 把历史消息作为知识库检索源(历史只用于改写上下文与回溯展示)
- 多用户与鉴权(保持单用户 demo 定位)
- "事后补转换"按钮(上传时未启用 MinerU 的文件, v1 不补转)

## Decisions

### D1. MySQL 驱动:PyMySQL,单连接 + 每次请求前 ping

纯 Python 实现,零编译依赖;demo 单用户负载下用模块级单连接,每次使用前 `conn.ping(reconnect=True)`。备选:SQLAlchemy(带连接池,对 demo 过重)、mysql-connector-python(体积更大,无额外收益)。

### D2. 两表结构,来源与 meta 用 JSON 列

```sql
sessions(id BIGINT AUTO_INCREMENT PRIMARY KEY,
         title VARCHAR(200) NOT NULL,
         created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
         updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP)
messages(id BIGINT AUTO_INCREMENT PRIMARY KEY,
         session_id BIGINT NOT NULL,           -- FK -> sessions(id), 级联删除
         role ENUM('user','assistant') NOT NULL,
         content MEDIUMTEXT NOT NULL,
         sources JSON NULL,                    -- assistant 消息存,格式同 /chat 响应
         meta JSON NULL,                       -- 同上
         created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
         INDEX idx_session (session_id, id))
```

会话标题取首问前 20 字,创建时即定。备选:单表 + session 字符串列(查询/级联删除别扭,弃)。

### D3. 存储层落在独立模块,API 层组装历史

新增 `app/core/db.py`(连接、建表、会话/消息 DAO)与 `app/api/sessions.py`(会话路由)。`/chat` 流程改为:`chat.py` 校验 session → 读该会话最近 `HISTORY_WINDOW*2` 条消息 → 以 `pipeline.query(question, history)` 调用(签名不变,pipeline 与 pre_query 不感知 MySQL)→ 响应后将 user/assistant 两条消息落库。分层保持:pipeline 仍可脱离数据库独立运行。

### D4. 落库为尽力而为

答案已生成后若落库失败,不回滚不报 500:记日志告警、响应照常返回(避免存储故障毁掉一次成功的问答)。会话/消息查询接口在 MySQL 不可用时返回 503。风险表见下。

### D5. MySQL 容器独立部署,不并入 milvus_demo

`docker run` 独立 MySQL 8 容器,数据卷持久化到 `~/mysql-data`,避免跨项目修改 `open-ai-demo/milvus_demo` 的 compose 文件。`.env` 新增 `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE`,全部走 `_need` 快速失败;`db.py` 启动时自动 `CREATE DATABASE IF NOT EXISTS` + `CREATE TABLE IF NOT EXISTS`(沿用 milvus_client 的"启动即可用"模式)。

### D6. `/chat` 破坏性变更随前端同仓切换

无外部 API 消费者,前后端同一 commit 切换:请求体 `{question, history}` → `{question, session_id}`,多余 `history` 字段静默忽略(Pydantic 默认行为,天然满足 spec)。

### D7. 前端拆分:index.html + manage.html + style.css

- `static/style.css`:抽公共样式(侧边栏、按钮、toast、消息气泡),两页共用
- `index.html`:侧边栏 = 标题/状态 + 会话列表(新建/切换/删除)+ 管理页入口 + 清空当前会话;聊天区 `append()` 渲染逻辑不动(来源 + meta 照旧)。切换会话时拉 `GET /sessions/{id}/messages` 回显历史(用持久化的 sources/meta 渲染,与实时回答同一渲染路径)
- `manage.html`:双 tab。文件管理(上传/目录入库/列表/统计,逻辑从首页原样搬移)+ 问答历史(会话列表 → 消息列表,展开来源/meta)。历史 tab 与首页共用同一消息渲染结构
- 会话管理的 fetch 调用两页都会用到,抽 `static/app.js` 共享(会话列表渲染 + 消息渲染函数),避免双份拷贝

### D8. 转换产物接口:路径白名单校验

`GET /upload/converted/{name}`:对 `name` 先取 `basename`(拒绝目录分隔符),`resolve()` 后必须位于 `MINERU_OUTDIR` 之下且后缀为 `.md`,否则 404;存在才返回内容。`GET /upload/files` 每项扩展 `has_converted` 字段:`MINERU_ENABLED` 且 `converted_md_path()` 存在时为 true,前端据此渲染"查看转换结果"入口。未启用 MinerU 时管理页显示提示条说明原因。

## Risks / Trade-offs

- [MySQL 服务不可用] → 问答降级可用(落库失败仅告警);会话/历史接口返回 503 并在前端 toast 提示
- [连接因超时被服务端断开] → 每次使用前 `ping(reconnect=True)`
- [JSON 列体积] → sources 片段在生成端已截断(300 字符),meta 为小型对象,MEDIUMTEXT + JSON 列容量充足
- [BREAKING 前后端失同步] → 同仓同 commit 部署;`history` 字段被忽略而非报错,降低半升级态的爆炸半径
- [独立 MySQL 容器增加运维项] → 与 Milvus 同为 docker 服务,启动脚本/文档中并列说明
- [两页共享逻辑漂移] → 消息渲染与会话列表抽到 `static/app.js`,单一实现

## Migration Plan

1. 启动 MySQL 容器(独立 `docker run`,数据卷 `~/mysql-data`)
2. `.env` 追加 `MYSQL_*` 六项配置
3. 部署新代码(启动时自动建库建表,无需手工迁移)
4. 回滚:git revert 即可 —— 旧代码不依赖 MySQL,容器可留存不影响运行;历史数据在 MySQL 中保留,重升级后仍可读
