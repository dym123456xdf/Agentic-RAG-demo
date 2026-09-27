# Proposal: 删除目录扫描入库功能

## Why

管理页「索引服务器目录」功能(`POST /upload/dir`)接受任意服务器路径,递归读取后入库。三个问题叠加,这个端点不值得留:

1. **使用率极低** —— 当前真实工作流是前端拖拽上传,目录扫描是边缘场景;批量需求不强,用户已确认不需要替代。
2. **后端路径无沙箱** —— 任意路径都能触发 `pipeline.ingest(...)`,是服务暴露在 8011 端口下的无谓攻击面。
3. **原 spec 未声明** —— 是当年直接落到代码里的野口子,从未走规范(`openspec/specs/document-loading/spec.md` 里没有任何关于 `POST /upload/dir` 的 Requirement)。

直接删除,无替代方案。

## What Changes

- **BREAKING**: 删除 `POST /upload/dir` API 端点(后端 `app/api/upload.py:97-116`)
- **BREAKING**: 删除管理页「索引服务器目录」UI 区块(前端 `static/manage.html:36-40` HTML + `:214-235` JS 处理)
- 不动其他入库端点:`POST /upload/files` / `GET /upload/files` / `DELETE /upload/files/{name}` / `POST /upload/clear`
- 不引入替代实现(无 zip 上传、无多目录白名单)

## Capabilities

### New Capabilities
无。

### Modified Capabilities

- **`document-loading`**: 删除 `POST /upload/dir` 端点及管理页联动 UI。原 spec 未显式声明此端点(它是历史野口子),但作为对外可见 contract,删除需在 `specs/document-loading/spec.md` 用 `## Removed` 段标注,archive 后正式从主 spec 中移除。

## Impact

| 层 | 文件 | 操作 |
|---|---|---|
| 后端 | `app/api/upload.py:97-116` | 删 `@router.post("/dir")` 整段 + 文件头注释里"四个端点"改为"三个端点" |
| 前端 HTML | `static/manage.html:36-40` | 删 `<h3>索引服务器目录</h3>` + 输入框 + 「扫描并入库」按钮 |
| 前端 JS | `static/manage.html:214-235` | 删 `$("btnDir").onclick` 整段(loading 遮罩 / refreshFiles 等共享函数不动) |
| Spec delta | `specs/document-loading/spec.md` | 新增 `## Removed` 段,声明 `POST /upload/dir` 已移除 |
| 文档/docstring | 无 | — |
| 依赖 | 无 | — |
| 配置 | 无 | — |
| 数据迁移 | 无 | — |

用户感知:
- 管理页少一个区块(整个"索引服务器目录"输入框 + 按钮消失)
- 任何 `POST /upload/dir` 调用方(若有外部脚本/集成)会收到 404 —— 但本服务是单机自用,实际无外部调用方