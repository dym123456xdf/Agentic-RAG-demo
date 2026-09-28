# minio-storage Specification

## Purpose

把现有的本地 `uploads/`、`converted/` 目录全部迁移到 MinIO 对象存储:原文件与 MinerU 转换产物(md + images + assets)全部以对象形式落入 `rag-kb` 桶,桶策略设为 public-read 以兼容直连调试;前端原本通过 `/converted/<stem>/images/<file>` 访问图片的 URL 契约保留,由 FastAPI 后端代理路由从 MinIO 流式回放,前端零改动。

## ADDED Requirements

### Requirement: MinIO 客户端单例

系统 SHALL 在 `app/core/minio_client.py` 提供 `get_minio_client()` 单例,基于 `minio.Minio(endpoint, access_key, secret_key, secure=Config.MINIO_SECURE)`,配置从 `app/core/config.py` 读取 `MINIO_ENDPOINT / MINIO_ACCESS_KEY / MINIO_SECRET_KEY / MINIO_SECURE`;首次调用时执行 `ensure_bucket(bucket=Config.MINIO_BUCKET)`:桶不存在则创建,再设置 public-read 桶策略。

#### Scenario: 单例复用
- **WHEN** 任意两处调用 `get_minio_client()`
- **THEN** 返回同一实例,不在每次调用时新建连接

#### Scenario: 桶不存在自动创建
- **WHEN** `Config.MINIO_BUCKET = "rag-kb"` 且桶不存在
- **THEN** `make_bucket("rag-kb")` 后 `set_bucket_policy("rag-kb", public-read-policy)`,`bucket_exists` 返回 true

#### Scenario: 桶策略 public-read
- **WHEN** 桶策略已写入
- **THEN** 任意 `http://<endpoint>/<bucket>/<obj>` URL 可不带签名直连 GET,返回 200

### Requirement: 原文件与转换产物落桶

系统 SHALL 由 `app/api/upload.py` 把上传的原文件存入 `uploads/<name>` 对象;MinerU 转换产物(md、`images/`、`assets/`)按 `converted/<stem>/<stem>.md`、`converted/<stem>/images/<file>.<ext>`、`converted/<stem>/assets/<file>` 前缀分块入桶(注意:**无 `/auto/` 层级**,与前端 `/converted/<stem>/...` URL 契约一致);`minio.put_object(bucket, key, data, length)` 调用保证 `length > 0`。

#### Scenario: 原文件落桶
- **WHEN** 用户上传 `报告.pdf`
- **THEN** MinIO 出现 `uploads/报告.pdf` 对象,`stat_object` 返回 size > 0

#### Scenario: 转换产物落桶
- **WHEN** MinerU 转换完成
- **THEN** MinIO 出现 `converted/报告/报告.md`、`converted/报告/images/<hash>.jpeg` 等对象

#### Scenario: 空对象拒绝
- **WHEN** `length == 0` 的对象被尝试上传
- **THEN** 抛 `InvalidDataError` 或 `ValueError`,不入桶,日志记录文件名

### Requirement: 删除联动

系统 SHALL 由 `DELETE /upload/files/{name}` 同时清理:`uploads/<name>` 对象、`converted/<stem>/` 前缀下所有对象、Milvus 中 `doc_name == <name>` 的全部 chunk;`stem` 解析规则与 MinerU 产物布局一致(去扩展名)。

#### Scenario: 三处清理
- **WHEN** 调用 `DELETE /upload/files/报告.pdf`
- **THEN** MinIO 中 `uploads/报告.pdf` 被删除,`converted/报告/` 前缀下全部对象被 `remove_objects` 批量删除,Milvus 中 `doc_name == "报告.pdf"` 的全部 chunk 被 `delete(expr=...)` 删除

#### Scenario: 原文件不在桶
- **WHEN** `uploads/报告.pdf` 不存在但 `converted/报告/` 在桶中
- **THEN** 删除 API 不报错,继续清理 `converted/报告/` 与 Milvus

### Requirement: `/converted` 后端代理路由

系统 SHALL 在 `app/api/converted.py` 提供 FastAPI 路由 `GET /converted/{stem:path}`,从 MinIO 流式回放对应对象;`main.py` SHALL 移除原 `app.mount("/converted", StaticFiles(...))`,改为 `app.include_router(converted_router)`;URL 契约与原本地 static mount 完全一致(`/converted/<stem>/images/<file>.<ext>` 等)。

#### Scenario: 图片 URL 可 HTTP GET
- **WHEN** 浏览器请求 `/converted/报告/images/<hash>.jpeg`
- **THEN** 返回 200 + `image/jpeg`,内容来自 MinIO `converted/报告/images/<hash>.jpeg`,**非** 本地文件系统

#### Scenario: 防路径穿越
- **WHEN** 浏览器请求 `/converted/../etc/passwd` 或 `/converted/<stem>/../../../etc/passwd`
- **THEN** 路由不构造跨桶路径,返回 404,不返回任何文件

#### Scenario: MIME 推断
- **WHEN** 对象后缀为 `.md / .jpeg / .png / .json`
- **THEN** 响应 `Content-Type` 分别为 `text/markdown; charset=utf-8` / `image/jpeg` / `image/png` / `application/json`

#### Scenario: 大文件流式
- **WHEN** 对象 size 较大(> 5 MB,如 md + 多图合并产物)
- **THEN** 响应使用 `StreamingResponse(minio.get_object(...).stream(...))`,不一次性读入内存

### Requirement: 移除本地目录依赖

`uploads/`、`converted/` 本地目录 SHALL 不再被任何业务路径写入或读取;`Config.MINERU_OUTDIR` 改为 MinIO 临时落盘的本地 staging 目录(仅 MinerU 转换期间使用),转换完成后立即上传到 MinIO 并删除 staging 目录。

#### Scenario: 不再写本地 uploads
- **WHEN** `POST /upload/files` 被调用
- **THEN** 不在 `Config.UPLOADS_DIR` 下创建文件,直接 `minio.put_object(...)` 入桶

#### Scenario: staging 目录仅过渡
- **WHEN** MinerU 转换完成
- **THEN** `converted/<stem>/` 内容已被上传 MinIO,`Config.MINERU_OUTDIR/<stem>/` staging 目录被 `shutil.rmtree` 删除

### Requirement: `.env` 配置

系统 SHALL 由 `app/core/config.py` 暴露以下 `.env` 字段:`MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`、`MINIO_BUCKET`、`MINIO_SECURE`(bool,默认 false);字段缺失时初始化快速失败。

#### Scenario: 字段读取
- **WHEN** 任意代码读取 `Config.MINIO_ENDPOINT`
- **THEN** 返回 `.env` 中的字符串(如 `127.0.0.1:9000`),与启动时配置一致

#### Scenario: 启动失败
- **WHEN** `MINIO_ENDPOINT` 为空
- **THEN** `Config` 在 import 时抛 `RuntimeError("MINIO_ENDPOINT not configured")`,FastAPI 启动失败
