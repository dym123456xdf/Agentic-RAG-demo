# Tasks

## 1. 后端删除能力

- [x] 1.1 `app/core/milvus_client.py` 新增 `delete_source(name) -> int`:`MilvusClient.delete(collection, filter=f'source == "{escaped}"')`,`"` 转义;collection 不存在返回 0
- [x] 1.2 `app/api/upload.py` 新增 `DELETE /upload/files/{name}`:name 白名单校验(basename、无 `/`、后缀在 `ALLOWED_EXTS`),Milvus 先删、磁盘容错(`uploads/<name>` 与 `converted/<stem>/` missing_ok),两者皆无且 Milvus 计数 0 → 404;响应 `{deleted, chunks_removed}`

## 2. 前端删除按钮

- [x] 2.1 `static/manage.html` `refreshFiles()` 行内追加 `.del-file` trash SVG 按钮(`data-name`);`fileList.onclick` 委托先判 `.del-file` → confirm("不可恢复")→ `DELETE /upload/files/<name>` → toast + `refreshFiles()`
- [x] 2.2 `static/style.css` 加 `.file-list .del-file`(默认 `--text-secondary`、hover `--danger`),对齐 `.session-list .del` 先例

## 3. 验证

- [x] 3.1 启动服务,管理页删除一个文件:Milvus chunk 数归零、`uploads/` 与 `converted/<stem>/`(含 assets/)消失、`GET /upload/files` 列表与统计同步更新
- [x] 3.2 负路径:`DELETE /upload/files/..%2F..%2Fetc`、不存在的文件名、带 `/` 的名称 → 404;01 残留(Milvus 有、磁盘无)可删且 200
- [x] 3.3 幂等闭环:删除后重传同名文件,`POST /upload/files` 重新入库(不跳过)且 chunks 数正确
