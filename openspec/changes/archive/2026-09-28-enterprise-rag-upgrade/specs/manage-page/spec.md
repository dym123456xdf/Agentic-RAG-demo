# Spec Delta

## Purpose

管理页文件删除链路与转换产物读取链路的数据载体由本地磁盘迁移到 MinIO 对象存储;管理页 UI 与 HTTP 接口契约不变,内部清理与读取路径改为走 `app/core/minio_client.py` 与 `app/api/converted.py` 后端代理路由。

## MODIFIED Requirements

### Requirement: 删除已入库文件

管理页文件列表 SHALL 对每个已入库文件提供删除入口;删除接口 `DELETE /upload/files/{name}` SHALL 联动清除三处:① Milvus 中 `doc_name == <name>` 的全部 chunk;② MinIO `uploads/<name>` 对象;③ MinIO `converted/<stem>/` 前缀下全部对象(含 md、`images/`、`assets/`,由 `remove_objects` 批量删除)。本地磁盘 SHALL 不再被读写;删除前 SHALL 有不可恢复确认,成功后刷新列表并提示。

#### Scenario: 删除后三处全部清除
- **WHEN** 用户在管理页删除一个已入库且含转换产物的文件
- **THEN** Milvus 中该 source 的 chunk 计数归零,MinIO `uploads/<name>` 与 `converted/<stem>/` 前缀下对象全部清空,`GET /upload/files` 列表与统计同步更新

#### Scenario: 删除前确认
- **WHEN** 用户点击某文件的删除按钮
- **THEN** 弹出不可恢复确认,取消则不删除,确认后执行

#### Scenario: 删除后重传生效
- **WHEN** 某文件被删除后,用户重新上传同名文件
- **THEN** 新文件内容被重新入库(不被幂等跳过),chunk 数按新内容计算

#### Scenario: 脏数据可清理
- **WHEN** MinIO 源文件已丢失但 Milvus 仍有该 source 的 chunk(历史残留)
- **THEN** 删除接口仍返回成功并清掉 Milvus 侧 chunk,MinIO 不存在的对象不报错

#### Scenario: 非法文件名拒绝
- **WHEN** 删除接口收到含路径分隔符、`..` 或不在允许后缀白名单内的名称
- **THEN** 返回 404,不发生任何删除

### Requirement: 转换产物人工核对

管理页的文件列表 SHALL 对存在 MinerU 转换产物的文件(PDF/DOCX/PPTX)提供"查看转换结果"入口,点击后展示 MinIO `converted/<stem>/<stem>.md` 对象的完整内容,供人工核对转换准确性;内容中的图片相对引用 SHALL 被改写为 `/converted/<stem>/images/<file>.<ext>` 绝对 URL 并渲染为真实图片(URL 仍走 `minio-storage` 规格定义的后端代理路由,前端零改动)。

#### Scenario: 查看转换产物
- **WHEN** 用户点击某 PDF 文件的"查看转换结果"
- **THEN** 页面展示该文件对应的转换 Markdown 全文,内容来源为 MinIO `converted/<stem>/<stem>.md` 对象

#### Scenario: 弹层内图片显示
- **WHEN** 转换产物 md 含 `![image](images/xxx.png)` 相对引用
- **THEN** 弹层渲染时该引用变为 `<img src="/converted/<name>/images/xxx.png">`,浏览器能拉到并显示真实图片,而非 `![...]` 语法原文或裂图

#### Scenario: 文本内容仍可读
- **WHEN** 弹层渲染含图片的 md
- **THEN** 标题、段落、表格、代码块都正常显示,文本不会被图片破坏排版

#### Scenario: 原生文本文件无入口
- **WHEN** 已入库文件为 `.md`/`.markdown`/`.txt` 等原生文本
- **THEN** 该文件不显示"查看转换结果"入口

#### Scenario: 未启用 MinerU 时无入口
- **WHEN** 服务配置未启用 MinerU(`MINERU_ENABLED=false`)
- **THEN** 文件列表中任何文件都不显示"查看转换结果"入口

### Requirement: 转换产物接口的访问安全

转换产物读取接口 SHALL 只允许访问 MinIO 桶内 `converted/` 前缀的 `.md` 对象;任何路径穿越尝试必须被拒绝(不构造跨桶路径、不响应对象内容)。

#### Scenario: 拒绝路径穿越
- **WHEN** 请求的文件名包含 `..`、绝对路径或目录分隔符
- **THEN** 接口返回 400/404 错误,不返回任何文件内容

#### Scenario: 请求不存在的产物
- **WHEN** 请求的文件名在 MinIO 桶 `converted/` 前缀下不存在对应对象
- **THEN** 接口返回 404 错误
