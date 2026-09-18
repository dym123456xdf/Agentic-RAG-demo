# Spec Delta

## Purpose

规定 MinerU 转换产物的目录布局契约(每文档一个无后缀文件夹,md 与图片同级),以及入库文本中图片引用的 URL 形态:切分入库的文本必须携带可直接访问的绝对 URL,使检索回来的片段脱离来源文件上下文后,图片引用依然可被前端解析加载。

## MODIFIED Requirements

### Requirement: MinerU 产物落盘与图片抽取

一份文档的 MinerU 产物 SHALL 集中在 `converted/<stem>/` 单一文件夹内(`stem` 为原文件名去掉后缀):md 产物为 `converted/<stem>/<stem>.md`,图片为 `converted/<stem>/images/<file>`,两者同级;`converted/` 顶层不再存放任何产物文件。`mineru-kit parse` 产物 md 里的 base64 内嵌图 SHALL 被抽取到该 `images/` 目录并在文本中替换为 `images/<hash>.<ext>` 相对引用;产物已存在时直接复用,不重复转换。

#### Scenario: 转换产物的落盘布局
- **WHEN** 一份名为 `报告.pdf` 的文档转换完成
- **THEN** md 落在 `converted/报告/报告.md`,图片落在 `converted/报告/images/` 下,`converted/` 顶层无散落的 md 文件

#### Scenario: 上传接口按新布局定位产物
- **WHEN** 管理页请求某 PDF 的转换产物(`has_converted` 判定与转换产物读取接口)
- **THEN** 系统按 `converted/<stem>/<stem>.md` 定位并返回内容,旧顶层路径不再被使用

#### Scenario: 图片落盘 + 路径替换
- **WHEN** 转换产物 md 含 `![](data:image/jpeg;base64,<base64string>)`
- **THEN** 后处理将 base64 解码为 jpeg 字节,写到 `converted/<stem>/images/<8字符hash>.jpeg`,md 文本该处被替换为 `images/<8字符hash>.jpeg`

#### Scenario: 多图按出现顺序落盘
- **WHEN** 一份 PDF 含 N 张图
- **THEN** `converted/<stem>/images/` 下生成 N 个文件,md 文本 N 处 base64 引用都被替换

#### Scenario: 落盘后 md 总大小明显小于 base64 内嵌
- **WHEN** 同一 PDF 转换产物对比
- **THEN** 经后处理的 md 文件大小应 < base64 内嵌版本的 30%(实测 7.9MB → 数十 KB)

#### Scenario: 产物已存在时跳过转换
- **WHEN** `converted/<stem>/<stem>.md` 已存在
- **THEN** 不调 mineru,直接返回该路径

## ADDED Requirements

### Requirement: 入库文本图片引用规范化为绝对 URL

经 MinerU 通道转换入库的文档,进入切分与向量库的文本中,形如 `![alt](images/<file>)` 的相对图片引用 SHALL 被改写为 `![alt](/converted/<stem>/images/<file>)` 绝对 URL;落盘的 md 产物 SHALL 保持相对路径不变(人工核对与"查看转换结果"弹层行为不受影响)。

#### Scenario: 入库 chunk 含绝对 URL
- **WHEN** 一份含图 PDF 经上传入库完成
- **THEN** 向量库中该文档的 chunk 文本里图片引用形如 `![image](/converted/<stem>/images/<hash>.<ext>)`,不再是 `images/...` 相对路径

#### Scenario: 落盘产物保持相对路径
- **WHEN** 同一份 PDF 转换完成
- **THEN** `converted/<stem>/<stem>.md` 中的图片引用仍为 `images/<hash>.<ext>` 相对路径,文件内容不因本变更改变

#### Scenario: 已有产物复用时同样改写
- **WHEN** `converted/<stem>/` 下已存在该文件的转换产物,重新上传入库(产物直接复用)
- **THEN** 入库 chunk 文本中的图片引用仍被规范化为绝对 URL

### Requirement: 原生 Markdown 直传不做路径改写

`.md` / `.markdown` 文件直传入库时,其文本中的图片引用 SHALL 保持原样,不做任何路径改写或搬运(此类文件的图片语义由作者自行负责,系统不猜测其存放位置)。

#### Scenario: 直传 md 引用不被改写
- **WHEN** 用户直传一份图片引用为 `./assets/a.png` 的 `.md` 文件并入库
- **THEN** 向量库中该文档 chunk 的文本保留 `./assets/a.png` 原文
