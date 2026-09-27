# Spec Delta: document-loading

## REMOVED Requirements

### Requirement: 目录扫描入库端点 `POST /upload/dir`

系统 SHALL 提供一个 `POST /upload/dir` 接口,接收 JSON `{ "path": "<服务器路径>" }`,递归读取该路径下的支持格式文件并入库(支持相对路径,基准为项目根)。该端点同时由管理页「索引服务器目录」UI 区块联动使用(路径输入框 + 「扫描并入库」按钮)。

#### Scenario: 端点接收路径并入库

- **WHEN** 客户端以 `Content-Type: application/json` POST `{ "path": "data/" }` 到 `/upload/dir`
- **THEN** 系统按 `data/` 相对项目根解析为绝对路径,递归读取该目录下所有白名单扩展名(PDF / DOCX / PPTX / MD / TXT)文件,经 `pipeline.ingest(path)` 入库,响应包含 `ingested_from` / `chunks_ingested` / `skipped_files` 字段

#### Scenario: 路径不存在时返回 404

- **WHEN** 客户端 POST 的 `path` 在服务器上不存在
- **THEN** 系统返回 404 + `路径不存在: <绝对路径>`

#### Scenario: 管理页联动 UI

- **WHEN** 用户在管理页「索引服务器目录」输入框填入路径并点击「扫描并入库」
- **THEN** 前端 `POST /upload/dir` 触发,期间显示 loading 遮罩;完成后 toast 提示「从 <路径> 入库 N 个片段」并刷新文件列表

**Reason**: 原 spec 未声明此端点(它是历史野口子,直接落到生产代码里从未走过规范)。三个问题叠加导致该能力不值得保留:

1. **使用率极低** —— 当前真实工作流是前端拖拽上传,目录扫描是边缘场景,用户已确认不需要替代批量方案。
2. **后端路径无沙箱** —— 任意路径都能触发 `pipeline.ingest(...)`,在服务暴露于 8011 端口下构成无谓的攻击面(本地自用也有踩坑风险)。
3. **无替代价值** —— 批量入库已可通过 `POST /upload/files` 的 multipart 多文件上传实现,前端 `<input type="file" multiple>` 已支持多选。

**Migration**: 无外部调用方(本服务是单机自用,API 仅供管理页调用,管理页同步删除该 UI 区块)。`POST /upload/dir` 收到任何请求将返回 404 Method Not Allowed / 路由不存在;批量入库场景改用「上传文件入库」区块的多文件选择/拖拽。无需数据迁移、无需配置变更。