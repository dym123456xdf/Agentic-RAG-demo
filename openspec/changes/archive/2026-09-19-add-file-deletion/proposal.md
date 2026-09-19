# Proposal

## Why

入库文件只进不出:想移除一个文件得手工连 Milvus 删 chunk、手工删 `uploads/` 文件、手工删 `converted/<stem>/` 产物,三处缺一即不一致。且幂等去重按 Milvus `source` 字段,同名文件重传被静默跳过——内容改了也更新不了索引(项目既有硬约束)。01-LangChain概述.pdf 的残留索引(磁盘文件已删、Milvus 仍有 87 chunk)只能靠手工清。

## What Changes

- 新增 `DELETE /upload/files/{name}`:一次联动删除该 source 在 Milvus 的全部 chunk + `uploads/<name>` 物理文件 + `converted/<stem>/` 整目录(含 md、images/、assets/);文件不在索引中 404,非法文件名(`../`、分隔符)404
- `MilvusStore` 新增 `delete_source(name) -> int`,经 `MilvusClient.delete(filter=source == ...)` 删除,返回删除 chunk 数
- 管理页文件列表每行加删除按钮(trash 内联 SVG currentColor,danger 语义,hover 变红),点击先原生 confirm,成功后 toast + 刷新列表
- 删除后重传同名文件不再被幂等跳过,内容更新随之生效

## Capabilities

### Modified Capabilities

- `manage-page`:文件管理区块新增"删除已入库文件"能力(API + 列表删除按钮)

注:`document-loading` 无 delta——入库幂等语义不变(删除后 Milvus 里无该 source,自然不再命中跳过),只是既有幂等规则在新前提下自然生效。

## Impact

- **后端**:`app/core/milvus_client.py`(+`delete_source`)、`app/api/upload.py`(+`DELETE /upload/files/{name}`)
- **前端**:`static/manage.html`(列表行删除按钮 + 事件委托)、`static/style.css`(`.file-list .del-file`)
- **数据**:删除不可逆,无回收站;Milvus chunk、磁盘文件、转换产物三者一并清除
- **兼容**:纯新增能力,不影响既有入库/检索链路
