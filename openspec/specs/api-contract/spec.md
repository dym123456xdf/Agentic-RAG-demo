# api-contract Specification

## Purpose
定义 HTTP API 的请求/响应契约，确保前后端对接一致。

## Requirements

### Requirement: POST /chat
系统 SHALL 接收 {question, history[]} 并返回 {answer, sources[], meta}。

#### Scenario: 正常提问
- **WHEN** POST /chat {"question": "什么是 embedding?", "history": []}
- **THEN** 返回 200
- **AND** body.answer 为字符串
- **AND** body.sources 为数组，每项含 index/content/score/source
- **AND** body.meta 含 intent/rewritten/expanded/raw_count/after_count

#### Scenario: 缺少 question
- **WHEN** POST /chat 不含 question 字段
- **THEN** 返回 422 校验错误

### Requirement: POST /upload/files
系统 SHALL 接收 multipart 文件列表并返回入库统计。

#### Scenario: 成功入库
- **WHEN** POST /upload/files 上传合法文件
- **THEN** 返回 {saved: [文件名], files, chunks_ingested, skipped_files, total_entities}

### Requirement: GET /upload/files
系统 SHALL 返回已入库文件列表。

#### Scenario: 返回列表
- **WHEN** GET /upload/files
- **THEN** 返回 {files: [{name, chunks}], file_count, total_chunks}

### Requirement: 静态页
系统 SHALL 在 GET / 返回 static/index.html，在 /static/ 提供静态资源。

#### Scenario: 首页
- **WHEN** GET /
- **THEN** 返回 index.html 文件内容

#### Scenario: index.html 不存在
- **GIVEN** static/index.html 不存在
- **WHEN** GET /
- **THEN** 返回 {"msg": "static/index.html missing"}
