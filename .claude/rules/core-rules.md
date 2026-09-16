# .claude/rules/core-rules.md

> Claude 在本项目工作时**必须遵守**的行为规则。
> 与项目信息分离(项目信息在 `CLAUDE.md`)。改这里之前先看是否该归入 openspec change。

## 改代码之前

- 必读 `openspec/changes/` 下相关 proposal;没有就建一个(`openspec/changes/<name>/`)
- 改 `app/` 任何文件前,确认对应的 spec 在 `openspec/specs/` 里有契约
- 不直接改 `openspec/specs/` 下的文件 — 走 change → archive 流程
- `app/core/config.py` 改了 `.env` 字段必须同步 `CLAUDE.md` §Build / Verify

## RAG 流水线硬约束

- **入库与检索必须用不同编码空间**:`_get_text_embedding` 强制 `type_="db"`,`_get_query_embedding` 强制 `type_="query"`。混用 = 召回率暴跌。
- **Embedding 协议与 OpenAI 不兼容**(`embo-01` 三处硬差异):请求体字段 `texts`/`type`、GroupId 走 URL query、响应 `vectors[]`。改 `app/core/embedding.py` 必须保留这三处,不能"统一成 OpenAI 风格"。
- **Markdown 按标题切,不用定长切**:`MarkdownNodeParser` 会塞 `header_path` 等额外元数据,`indexer.py` 入库前显式清洗只留 `source` + `doc_id`,否则 Milvus 报未注册字段。
- **Milvus 余弦距离 ∈ [0, 2],值越小越相关**。`SIMILARITY_CUTOFF=2.0` 默认"全过"。不要用 llama-index 的 `SimilarityPostprocessor`(语义反了)。
- **M3 输出 `...` 推理块**:`app/core/llm.py` 的 `strip_thinking()` 全局剥掉,任何新增 LLM 调用都必须走 `LLMClient`,不要绕过去自己 `OpenAILike()`。
- **`MILVUS_DB` 当前未生效**(`MilvusVectorStore` 不传 db_name,数据写 default DB)。改 `app/core/milvus_client.py` 之前必读 `openspec/changes/fix-milvus-db-name-ignored/`。

## 上传与入库

- **幂等**:`app/rag/indexer.py` 按文件名去重,二次上传同名文件不重新 embedding
- **后缀白名单**:`Config.ALLOWED_EXTS` = `{".pdf", ".md", ".markdown", ".docx", ".pptx", ".txt"}`。新增类型必须改 config + openspec/specs/document-indexing
- **路径穿越防御**:`app/api/upload.py` 只取 `Path(f.filename).name`,不接收子目录路径
- **MinerU 开关(`MINERU_ENABLED`)已就位但 loader 未接通**:`true` 与 `false` 行为相同。要接通按 `openspec/changes/wire-mineru-pipeline/tasks.md` 走

## 输出规范

- 中文回答用户(本仓库惯例:README / CLAUDE.md / 中文 docstring + 英文代码标识符)
- OpenSpec 文件:正文中文,保留 `### Requirement` / `#### Scenario` / `**WHEN**` / `**THEN**` / `**SHALL**` 等规范关键词英文
- 不用 emoji / 不用破折号"——"以外的装饰符号 / 不写"sycophantic opener"
- 不要重新读未改过的文件

## 不该做的事

- 不创建 `.claude/settings.json` 的 hooks / 不动用户级 `~/.claude/`(改所有会话行为,风险/收益不匹配)
- 不创建 `CLAUDE.local.md` 占位(那是个人偏好,不该预设)
- 不为本次修改扩 memory/ 子系统(YAGNI,本项目没跨 worktree 需求)
- 不 amend 上次 CLAUDE.md 重写 commit(保留审计链)
