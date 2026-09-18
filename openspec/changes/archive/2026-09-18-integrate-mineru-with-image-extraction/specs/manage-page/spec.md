# Spec Delta

## Purpose

管理页"查看转换结果"弹层从纯文本 `<pre>` 升级为可渲染图片的视图:md 里的 `images/<hash>.<ext>` 相对引用自动改写为 `/converted/<name>/images/...` 绝对 URL,人工核对时能直接看到 MinerU 抽出的真实图片。

## MODIFIED Requirements

### Requirement: 转换产物人工核对

管理页的文件列表 SHALL 对存在 MinerU 转换产物的文件(PDF/DOCX/PPTX)提供"查看转换结果"入口,点击后展示 `converted/` 目录下对应 Markdown 的完整内容,供人工核对转换准确性;内容中的图片相对引用 SHALL 被改写为可加载的绝对 URL 并渲染为真实图片。

#### Scenario: 查看转换产物
- **WHEN** 用户点击某 PDF 文件的"查看转换结果"
- **THEN** 页面展示该文件对应的转换 Markdown 全文

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
