# Spec Delta

## Purpose

迁移到 MinIO 对象存储后,MinerU 转换产物的本地 `converted/<stem>/` 目录不再作为最终落地位置,改为仅作 MinerU 子进程的临时 staging(转换完成即被上传 MinIO 并删除);同步移除原本依赖本地 static mount 的 `/converted` 路由契约,改为由 `minio-storage` 规格的后端代理路由接管,前端 URL 契约保留。

## MODIFIED Requirements

### Requirement: MinerU 产物落盘与图片抽取

一份文档的 MinerU 产物 SHALL 先集中在 `Config.MINERU_OUTDIR/<stem>/` 单一 staging 文件夹内(`stem` 为原文件名去掉后缀):md 产物为 `<stem>.md`,图片为 `images/<file>`;`MINERU_OUTDIR/` 顶层不再存放任何产物文件。`mineru-kit parse` 产物 md 里的 base64 内嵌图 SHALL 被抽取到该 `images/` 目录并在文本中替换为 `images/<hash>.<ext>` 相对引用;转换产物在上传 MinIO 之前由入库图 `pdf_to_md` + `md_img` 节点产出,转换完成后 SHALL 由 `ingest` 流程把整目录上传到 MinIO `converted/<stem>/` 前缀(**无 `/auto/` 层级**,与前端 URL 契约一致),并删除本地 staging 目录。

#### Scenario: 转换产物的落盘布局
- **WHEN** 一份名为 `报告.pdf` 的文档转换完成
- **THEN** md 落在 `MINERU_OUTDIR/报告/报告.md`,图片落在 `MINERU_OUTDIR/报告/images/` 下,`MINERU_OUTDIR/` 顶层无散落的 md 文件

#### Scenario: staging → MinIO 上传 + 本地清理
- **WHEN** staging 目录转换完成后入库图继续执行
- **THEN** `MINERU_OUTDIR/报告/` 内容被批量上传到 MinIO `converted/报告/`,本地 staging 目录被 `shutil.rmtree` 删除,磁盘不再保留

#### Scenario: 落盘后 md 总大小明显小于 base64 内嵌
- **WHEN** 同一 PDF 转换产物对比
- **THEN** 经后处理的 md 文件大小应 < base64 内嵌版本的 30%(实测 7.9MB → 数十 KB)

#### Scenario: 图片落盘 + 路径替换
- **WHEN** 转换产物 md 含 `![](data:image/jpeg;base64,<base64string>)`
- **THEN** 后处理将 base64 解码为 jpeg 字节,写到 `MINERU_OUTDIR/<stem>/images/<8字符hash>.jpeg`,md 文本该处被替换为 `images/<8字符hash>.jpeg`

#### Scenario: 多图按出现顺序落盘
- **WHEN** 一份 PDF 含 N 张图
- **THEN** `MINERU_OUTDIR/<stem>/images/` 下生成 N 个文件,md 文本 N 处 base64 引用都被替换

#### Scenario: 上传接口按新布局定位产物
- **WHEN** 管理页请求某 PDF 的转换产物(`has_converted` 判定与转换产物读取接口)
- **THEN** 系统按 MinIO `converted/<stem>/<stem>.md` 定位并返回内容,旧顶层路径不再被使用

#### Scenario: 产物已存在时跳过转换
- **WHEN** `MINERU_OUTDIR/<stem>/<stem>.md` 已存在
- **THEN** 不调 mineru,直接复用该 staging,后续仍按"上传 MinIO + 删除 staging"流程走

## REMOVED Requirements

### Requirement: 静态文件路由 `/converted`

理由:该路由(`app.mount("/converted", StaticFiles(...))`)对应的本地 `converted/` 目录已不存在;URL 契约(`/converted/<stem>/images/<file>.<ext>`)由 `minio-storage` 规格定义的 FastAPI 后端代理路由接管,语义不变。

#### Scenario: 路由已被 MinIO 代理替换
- **WHEN** 浏览器请求 `/converted/<stem>/images/<file>`
- **THEN** 不再走 FastAPI static mount,而是命中 `app/api/converted.py` 的代理路由,从 MinIO 流式回放

#### Scenario: 防路径穿越
- **WHEN** 浏览器请求 `/converted/../etc/passwd` 或 `/converted/<name>/../../../etc/passwd`
- **THEN** 代理路由不构造跨桶路径,返回 404,不返回任何文件
