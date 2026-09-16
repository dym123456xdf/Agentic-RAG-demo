# Document Indexing — Future State (Wire MinerU)

> 本文件描述 `wire-mineru-pipeline` change 的 **未来状态**。
> 在本 change archive 时,会合并进 `openspec/specs/document-indexing/spec.md`。
> 在那之前,`openspec/specs/document-indexing/spec.md` 描述的是当前已部署行为(无 MinerU)。

## ADDED Requirements

### Requirement: Optional MinerU-backed parsing

When document parsing is configured to use MinerU, the system SHALL route `.pdf`, `.docx`, and `.pptx` files through the MinerU parser before ingestion.

#### Scenario: MinerU 启用且上传 PDF

- **WHEN** `MINERU_ENABLED` is true and the client uploads a PDF
- **THEN** the system SHALL invoke the MinerU binary against the file
- **AND** the resulting markdown SHALL be ingested using the same Markdown path as native `.md` files

#### Scenario: MinerU 关闭且上传 PDF

- **WHEN** `MINERU_ENABLED` is false (or unset) and the client uploads a PDF
- **THEN** the system SHALL fall back to the existing unstructured reader path
- **AND** behavior SHALL be identical to the pre-change baseline

#### Scenario: Markdown 文件不进 MinerU

- **WHEN** a `.md`, `.markdown`, or `.txt` file is uploaded
- **THEN** the system SHALL NOT invoke MinerU regardless of `MINERU_ENABLED`

### Requirement: MinerU output caching

The system SHALL cache MinerU's markdown output keyed by the source file's stem, so repeated uploads of the same file do not re-invoke the parser.

#### Scenario: 首次解析

- **WHEN** a PDF with stem `quarterly-report` is uploaded for the first time
- **THEN** MinerU SHALL be invoked
- **AND** the resulting markdown SHALL be persisted at `MINERU_OUTDIR/quarterly-report.md`

#### Scenario: 缓存命中

- **WHEN** a PDF with the same stem already has a cached markdown in `MINERU_OUTDIR`
- **THEN** the system SHALL NOT invoke MinerU
- **AND** the cached markdown SHALL be ingested directly

### Requirement: MinerU failure surfaces as error

The system SHALL treat MinerU failures as hard errors, not silent fallbacks.

#### Scenario: 二进制缺失

- **WHEN** MinerU is enabled but `MINERU_BIN` points to a non-existent file
- **THEN** the system SHALL return an error indicating the binary is missing
- **AND** the system SHALL NOT silently fall back to the unstructured reader

#### Scenario: 解析超时

- **WHEN** MinerU parsing exceeds `MINERU_TIMEOUT_S`
- **THEN** the system SHALL return a timeout error to the caller
- **AND** no partial markdown SHALL be persisted to the cache

#### Scenario: 退出码非零

- **WHEN** MinerU exits with a non-zero status
- **THEN** the system SHALL return an error including a short excerpt of stderr
- **AND** the failed file SHALL NOT be marked as ingested

### Requirement: MinerU images preserved but not indexed

The system SHALL leave MinerU's extracted image files on disk under `MINERU_OUTDIR` but SHALL NOT index image bytes into the vector store.

#### Scenario: Markdown 里的图片引用

- **WHEN** MinerU produces markdown containing image references such as `![caption](images/foo.png)`
- **THEN** those references SHALL be preserved verbatim in the indexed text
- **AND** the image files SHALL remain accessible at `MINERU_OUTDIR/<stem>/images/`
- **AND** no image bytes SHALL be written to Milvus