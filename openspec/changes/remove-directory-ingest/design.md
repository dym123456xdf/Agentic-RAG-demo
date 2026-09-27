# Design: 删除目录扫描入库功能

## Context

见 `proposal.md - Why`。当前状态约束:

- 后端 `app/api/upload.py` 同时暴露 5 个端点(`POST /upload/files`、`POST /upload/dir`、`GET /upload/files`、`DELETE /upload/files/{name}`、`POST /upload/clear`),本次只动其中一个,其他四个保留。
- 前端 `static/manage.html` 中存在「上传文件入库」+「索引服务器目录」+「已入库文件」三个区块,前两者独立、共享 `showLoading` / `hideLoading` / `refreshFiles` 等工具函数。本次删除「索引服务器目录」区块,**不删**共享工具函数(「上传文件入库」还在用)。
- `app/rag/loader.py::pipeline.ingest(str(path))` 本身是合法公共 API,本次不动 —— 真正移除的只有 HTTP 入口,`pipeline.ingest` 仍由 `POST /upload/files` 触发。

## Goals / Non-Goals

**Goals:**

- 完全移除 `POST /upload/dir` HTTP 端点(后端路由 + 注释里的"四个端点"措辞)
- 完全移除管理页「索引服务器目录」UI 区块(HTML + JS 事件绑定)
- 不影响其他入库/删除/列表端点,不引入替代实现

**Non-Goals:**

- 不收紧其他端点的路径策略(本次不动 `POST /upload/files` 的 `uploads/` 路径或 `pipeline.ingest` 本身)
- 不引入批量入库替代方案(无 zip 上传、无多目录白名单 —— 用户已确认不需要)
- 不改 `app/rag/` 下任何逻辑
- 不动 `static/index.html`(聊天首页)
- 不动 `static/style.css`(除非删除后某 CSS 选择器变成孤儿;实测 `.drop` / `.dir-row` / `#dirpath` 都仅在管理页用,`.drop` 仍被「上传文件入库」引用,`.dir-row` 和 `#dirpath` 可顺手清理)

## Decisions

**Decision 1: 删除顺序无所谓**

后端路由删除与前端 UI 删除互相独立,任一先后都不影响对方。

**Decision 2: 共享 UI 工具函数保留**

`showLoading` / `hideLoading` / `refreshFiles` / `escapeHtml` 等函数被「上传文件入库」区块、Tab 切换、重复上传模态、转换产物弹层等多个功能共用,本次删除**只移除 `$("btnDir").onclick` 整段**,其他函数定义不动。

**Decision 3: 端点路径不替换**

- 不把 `POST /upload/dir` 改成 410 Gone —— 因为没有调用方,直接 404 Method Not Allowed(FastAPI 默认)即可,最小化代码。
- 不加 deprecation header —— 同上,无调用方,无须提示。

**Decision 4: 前端 CSS 选择器顺手清理**

`static/style.css` 中 `.dir-row` 和 `#dirpath` 仅在「索引服务器目录」区块引用,删除区块后变成孤儿。本次 apply 阶段顺手清掉(在 tasks 里标一条)。`.drop` 因为「上传文件入库」还在用,**不动**。

**Decision 5: 不写新测试 / 不删测试**

仓库 `CLAUDE.md` 明确"没有 tests"。`openspec validate` 仅校验 spec 文本合规,不要求代码测试。本次 apply 阶段用 `python -c "import app.api.upload"` 导入冒烟 + 启动 `uvicorn` 看路由表不含 `/upload/dir` 即可。

## Risks / Trade-offs

- **[风险] 误删共享 UI 工具函数** —— 若 apply 时手抖把 `showLoading` 等一起删了,「上传文件入库」会立刻报错。
  → **Mitigation**: apply 时只删 `$("btnDir").onclick = async () => { ... };` 这一整段(manage.html:214-235),不动上下任何函数定义;启动服务后手动触发一次上传冒烟验证。

- **[风险] `pipeline.ingest` 仍接受任意路径,后端通过 `POST /upload/files` 间接暴露** —— 删除 `POST /upload/dir` 只是关掉了「直接传任意路径」的入口,但 `POST /upload/files` 接收的多文件最终仍由 `pipeline.ingest(str(Config.UPLOAD_DIR))` 处理,只限制在 `uploads/` 内。这其实是 OK 的:`uploads/` 是服务自身管理的目录,等价于沙箱化。
  → **Mitigation**: 不需要额外动作,本次删除已经去掉了最危险的"任意服务器路径"口子。

- **[回退] 误删后无法快速回退** —— 这是删除型变更,git revert 是唯一回退路径(因为 `POST /upload/dir` 被删了,运行时无法"恢复")。
  → **Mitigation**: apply 前确认分支干净、git status 无未提交改动;如需回退,`git revert HEAD` 即可。

## Migration Plan

无部署步骤(单机自用服务)。无数据迁移。无配置变更。无回滚脚本(`git revert` 即回滚)。

## Open Questions

无。