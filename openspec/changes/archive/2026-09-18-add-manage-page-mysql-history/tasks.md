# Tasks

## 1. MySQL 基础设施

- [x] 1.1 启动 MySQL 8 容器(独立 `docker run`,数据卷 `~/mysql-data`,端口 3306),`docker ps` 确认 healthy、`nc -z localhost 3306` 可连通
- [x] 1.2 `.env` 追加 `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE`,`app/core/config.py` 以 `_need` 惯例暴露对应字段;未配置时启动报错信息清晰
- [x] 1.3 安装 PyMySQL 到 conda 环境 rag(`conda run -n rag pip install PyMySQL`),`python -c "import pymysql"` 通过

## 2. 存储层

- [x] 2.1 新建 `app/core/db.py`:模块级单连接 + `ping(reconnect=True)`、启动时自动 `CREATE DATABASE IF NOT EXISTS` + 建两表(sessions/messages,结构见 design D2);验证:启动服务后 `SHOW TABLES` 可见两表
- [x] 2.2 实现会话 DAO(创建/列表/删除/取单条)与消息 DAO(批量落库/按会话取最近 N 条/按会话取全部/清空会话);验证:用 `conda run -n rag python -c` 脚本走一遍 CRUD,重启服务后数据仍在

## 3. 会话 API

- [x] 3.1 新建 `app/api/sessions.py`:`POST /sessions`、`GET /sessions`、`DELETE /sessions/{id}`、`GET /sessions/{id}/messages`、`POST /sessions/{id}/clear`,MySQL 不可用返回 503;在 `main.py` 挂载路由。验证:curl 创建/列表/删除会话,响应结构与 spec 一致
- [x] 3.2 验证删除会话后消息级联清除、对已删会话查消息返回 404(curl 确认)

## 4. /chat 接口改造(BREAKING)

- [x] 4.1 `ChatRequest` 改为 `{question, session_id}`(多余 `history` 字段由 Pydantic 忽略),校验空问题返回 400、不存在会话返回 404;验证:curl 三种入参场景
- [x] 4.2 `chat.py` 在调用 `pipeline.query()` 前从存储读当前会话最近 6 条消息拼 `history`(pipeline 签名不变),响应后将 user/assistant 消息连同 sources/meta 落库,落库失败仅日志告警;验证:两轮提问(第二问含指代词)后查 `GET /sessions/{id}/messages`,meta.rewritten 已补全指代、消息完整落库
- [x] 4.3 全链路回归:curl `/chat` 正常问答,答案/来源/meta 结构与改造前一致

## 5. 转换产物查看接口

- [x] 5.1 `GET /upload/files` 每项扩展 `has_converted`(`MINERU_ENABLED` 且产物存在才为 true);验证:curl 对比 enabled/disabled 两种配置下的响应
- [x] 5.2 新增 `GET /upload/converted/{name}`:basename 白名单 + resolve 后必须位于 `MINERU_OUTDIR` 下且后缀 `.md`,否则 404;验证:curl 正常产物返回 200,`..%2f`、绝对路径、不存在文件均被拒

## 6. 前端共享层

- [x] 6.1 抽取 `static/style.css`(侧边栏、按钮、toast、消息气泡、来源/meta 块),两个页面引用后视觉与现版一致
- [x] 6.2 抽取 `static/app.js`:会话列表渲染、消息渲染(含来源与 meta,即现 `append()` 逻辑)、会话管理 fetch 封装;验证:两页引入后控制台无报错

## 7. 首页改造

- [x] 7.1 `static/index.html` 侧边栏替换为:标题/状态、会话列表(新建/切换/删除)、管理页入口、"清空当前会话";删除上传/目录入库/文件列表/统计区块;验证:打开首页仅见聊天 + 新侧栏
- [x] 7.2 发送提问改为携带 `session_id`、不再维护本地 `history` 数组;切换会话时拉历史消息用 `app.js` 渲染回显;验证:新建会话提问 → 切走再切回,问答记录完整含来源/meta;刷新页面后会话仍在(持久化)

## 8. 管理页

- [x] 8.1 新建 `static/manage.html` 文件管理 tab:拖拽/点击上传、目录入库、已入库列表(文件名 + chunk 数 + `has_converted` 入口)、向量统计,逻辑自首页搬移;验证:上传一个 md 一个 pdf,列表与统计正确刷新
- [x] 8.2 "查看转换结果"弹层:对 `has_converted` 文件调 `/upload/converted/{name}` 展示 Markdown 全文;`.md/.txt` 与 MinerU 未启用时不显示入口并显示提示条;验证:人工核对一份 PDF 的转换产物内容与 `converted/` 落盘文件一致
- [x] 8.3 问答历史 tab:会话列表 → 消息列表,单条问答可展开来源与 meta,空态有提示;验证:与首页同一会话的历史展示一致

## 9. 端到端验证

- [x] 9.1 完整链路演练:起 MySQL → 起服务 → 首页新建会话两轮提问 → 切换会话 → 管理页核对历史与转换产物 → 删除会话;服务重启后历史仍在
- [x] 9.2 破坏性确认:用旧请求体 `{question, history}` 调 `/chat` 确认被忽略不报错;停掉 MySQL 容器后确认问答仍可用、历史接口返回 503
