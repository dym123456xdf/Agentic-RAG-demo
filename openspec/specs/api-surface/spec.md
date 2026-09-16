# API Surface

暴露给前端 / 外部调用方的 HTTP 接口契约。

## Requirements

### Requirement: Document upload

The system SHALL expose a multipart upload endpoint accepting one or more files.

#### Scenario: Successful batch upload

- **WHEN** the client POSTs a multipart request with one or more supported files
- **THEN** the server SHALL save each file to the upload directory
- **AND** the server SHALL trigger ingestion for the batch
- **AND** the response SHALL report saved filenames plus ingestion counts

#### Scenario: Unsupported extension

- **WHEN** any uploaded file has an extension outside the allow-list
- **THEN** the server SHALL reject the request with HTTP 400
- **AND** the response SHALL name the offending file

### Requirement: Directory ingestion

The system SHALL expose an endpoint that ingests a server-accessible directory path.

#### Scenario: Valid directory

- **WHEN** the client POSTs a JSON body with a valid absolute or project-relative `path`
- **THEN** the server SHALL recursively walk the directory and ingest all supported files
- **AND** the response SHALL report the resolved path plus ingestion counts

#### Scenario: Missing path

- **WHEN** the client provides a path that does not exist on the server
- **THEN** the server SHALL respond with HTTP 404

### Requirement: Source listing

The system SHALL expose an endpoint listing already-ingested files and per-file chunk counts.

#### Scenario: List response

- **WHEN** the client calls the list endpoint
- **THEN** the response SHALL include the file count, total chunks, and an array of `{name, chunks}` entries sorted by name

### Requirement: Question answering

The system SHALL expose a JSON endpoint accepting a question plus optional history and returning a generated answer with sources and debug metadata.

#### Scenario: Request shape

- **WHEN** the client POSTs `{query: string, history?: ChatMessage[]}`
- **THEN** the server SHALL return `{answer: string, sources: SourceItem[], meta: object}`

#### Scenario: Meta field

- **WHEN** the response is generated
- **THEN** the `meta` field SHALL include preprocessing artifacts (intent, rewritten, expanded) and retrieval counts (raw and after-rerank)
- **AND** the `meta` field SHALL be safe to expose to end users (no internal secrets)

### Requirement: Pipeline singleton

The system SHALL maintain a single in-process pipeline instance across HTTP requests within a FastAPI worker process.

#### Scenario: Repeated requests

- **WHEN** the same client makes multiple requests to `/chat` or `/upload/*` within a process lifetime
- **THEN** the pipeline object SHALL be constructed exactly once
- **AND** cross-encoder and LLM clients SHALL NOT be re-initialized per request
