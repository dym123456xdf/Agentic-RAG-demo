# Document Indexing

把原始资料变成可检索的向量索引,支持多格式、幂等。

## Requirements

### Requirement: Multi-format loading

The system SHALL accept `.pdf`, `.md`, `.markdown`, `.docx`, `.pptx`, and `.txt` files for indexing.

#### Scenario: Markdown loaded directly

- **WHEN** a `.md` / `.markdown` / `.txt` file is ingested
- **THEN** the file SHALL be read as plain UTF-8 text
- **AND** heading markers (`#`) SHALL be preserved verbatim

#### Scenario: Binary formats loaded via reader

- **WHEN** a `.pdf` / `.docx` / `.pptx` file is ingested
- **THEN** the system SHALL use the unstructured reader to extract text
- **AND** the original filename SHALL be recorded as the document's `source` metadata

### Requirement: Markdown-aware splitting

The system SHALL split Markdown documents along heading boundaries so each chunk corresponds to one logical section.

#### Scenario: Markdown split by heading

- **WHEN** a Markdown document is split
- **THEN** the resulting chunks SHALL align with the document's heading hierarchy
- **AND** no chunk SHALL be cut mid-sentence

#### Scenario: Non-Markdown fallback

- **WHEN** a non-Markdown document is split
- **THEN** the document SHALL be treated as one chunk
- **AND** further splitting SHALL NOT be applied

### Requirement: Idempotent ingestion

Ingesting the same file twice SHALL NOT produce duplicate chunks in the index.

#### Scenario: Re-uploading an existing file

- **WHEN** a file with the same name is ingested twice
- **THEN** the second ingestion SHALL be a no-op for that file
- **AND** no additional embedding calls SHALL be made for it

#### Scenario: Mixed batch

- **WHEN** a batch contains both new and existing files
- **THEN** only the new files SHALL be embedded and indexed
- **AND** the response SHALL report which files were ingested and which were skipped

### Requirement: Source-only metadata

The system SHALL persist only `source` and `doc_id` as chunk metadata.

#### Scenario: Extra metadata fields

- **WHEN** a chunk carries metadata beyond `source` and `doc_id`
- **THEN** those fields SHALL be stripped before insertion
- **AND** the persistence layer SHALL NOT receive unregistered fields

### Requirement: Bootstrapping from existing collection

The system SHALL support starting queries without re-indexing when a collection already contains the documents.

#### Scenario: Cold start with existing collection

- **WHEN** the service starts and the collection is non-empty
- **THEN** the query path SHALL load the existing index
- **AND** no document files SHALL be re-read
- **AND** no embedding calls SHALL be made at startup

### Requirement: Single-source ingestion entry

The system SHALL expose a single entry point that runs loading, splitting, deduplication, embedding, and persistence in one call.

#### Scenario: Ingestion API surface

- **WHEN** a caller (HTTP route, CLI, test) wants to ingest files
- **THEN** it SHALL call exactly one function and receive a structured result with counts of files and chunks (ingested and skipped)
