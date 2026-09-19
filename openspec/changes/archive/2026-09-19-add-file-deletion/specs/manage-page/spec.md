# Spec Delta

## Purpose

管理页文件管理区块新增"删除已入库文件"能力,使入库文件可进可出,联动清除 Milvus 向量、磁盘源文件与转换产物。

## ADDED Requirements

### Requirement: 删除已入库文件

管理页文件列表 SHALL 对每个已入库文件提供删除入口;删除接口 `DELETE /upload/files/{name}` SHALL 联动清除该文件在 Milvus 中的全部 chunk、`uploads/<name>` 源文件、`converted/<stem>/` 转换产物目录(含 md、images/、assets/);删除前 SHALL 有不可恢复确认,成功后刷新列表并提示。

#### Scenario: 删除后三处全部清除
- **WHEN** 用户在管理页删除一个已入库且含转换产物的文件
- **THEN** Milvus 中该 source 的 chunk 计数归零,`uploads/<name>` 与 `converted/<stem>/` 磁盘实体不再存在,`GET /upload/files` 列表与统计同步更新

#### Scenario: 删除前确认
- **WHEN** 用户点击某文件的删除按钮
- **THEN** 弹出不可恢复确认,取消则不删除,确认后执行

#### Scenario: 删除后重传生效
- **WHEN** 某文件被删除后,用户重新上传同名文件
- **THEN** 新文件内容被重新入库(不被幂等跳过),chunk 数按新内容计算

#### Scenario: 脏数据可清理
- **WHEN** 磁盘源文件已丢失但 Milvus 仍有该 source 的 chunk(历史残留)
- **THEN** 删除接口仍返回成功并清掉 Milvus 侧 chunk,磁盘不存在的实体不报错

#### Scenario: 非法文件名拒绝
- **WHEN** 删除接口收到含路径分隔符、`..` 或不在允许后缀白名单内的名称
- **THEN** 返回 404,不发生任何删除
