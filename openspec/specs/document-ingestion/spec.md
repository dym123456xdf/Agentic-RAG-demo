# document-ingestion Specification

## Purpose
定义文档从上传/目录导入 → 解析 → 切分 → 向量化 → 写入 Milvus 的入库行为契约。

## Requirements

### Requirement: 文件上传
系统 SHALL 接收 multipart 文件上传，校验后保存到 uploads/ 并触发入库。

#### Scenario: 合法文件上传成功
- **WHEN** 上传 .pdf / .md / .docx / .pptx / .txt 后缀的文件
- **THEN** 文件保存到 uploads/
- **AND** 返回 saved 列表 + 入库统计

#### Scenario: 非法后缀拒绝
- **WHEN** 上传不在白名单后缀的文件
- **THEN** 返回 400 错误并说明不支持的格式

#### Scenario: 路径穿越防护
- **WHEN** 上传文件名包含子目录路径（如 `../../etc/passwd`）
- **THEN** 仅取 basename 保存，不写子目录

### Requirement: 目录导入
系统 SHALL 支持指定服务器上的目录路径，递归读取并入库。

#### Scenario: 路径不存在
- **WHEN** 指定的目录路径不存在
- **THEN** 返回 404 错误

#### Scenario: 相对路径解析
- **GIVEN** 传入相对路径 "data/"
- **WHEN** 服务器收到请求
- **THEN** 解析为项目根下的绝对路径并入库

### Requirement: 已入库文件列表
系统 SHALL 提供 GET /upload/files 端点，返回已入库文件名 + chunk 数。

#### Scenario: 列表展示
- **WHEN** 客户端请求 GET /upload/files
- **THEN** 返回 {files: [{name, chunks}], file_count, total_chunks}

### Requirement: 文档解析
系统 SHALL 根据 MinerU 开关决定 PDF/DOCX/PPTX 的解析后端。

#### Scenario: MinerU 开启
- **GIVEN** 环境变量 MINERU_ENABLED=true
- **WHEN** 上传 .pdf 文件
- **THEN** 使用 mineru 命令行工具解析为 markdown
- **AND** 转换结果存放在 converted/ 目录

#### Scenario: MinerU 关闭
- **GIVEN** 环境变量 MINERU_ENABLED=false
- **WHEN** 上传 .pdf 文件
- **THEN** 使用 UnstructuredReader 兜底解析

### Requirement: Markdown 切分
系统 SHALL 按标题层级切分文档，保证语义完整。

#### Scenario: Markdown 标题切分
- **WHEN** 文档包含 # / ## / ### 层级标题
- **THEN** 每个标题段切为独立 Node
- **AND** Node.metadata 保留 source 字段
