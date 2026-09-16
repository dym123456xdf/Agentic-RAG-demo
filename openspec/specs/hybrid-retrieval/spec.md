# Hybrid Retrieval

基于预处理产物从向量库捞相关片段,优先用扩展 query 提升召回覆盖。

## Requirements

### Requirement: Vector similarity retrieval

The system SHALL retrieve document chunks from the vector store whose cosine similarity to the query embedding is within the configured cutoff.

#### Scenario: Top-K results

- **WHEN** retrieval runs against a populated collection
- **THEN** the system SHALL return at most `TOP_K` results, ranked by ascending Milvus cosine distance

### Requirement: Query fusion

The system SHALL fuse retrieval across multiple query variants when more than one variant is available.

#### Scenario: Multiple variants

- **WHEN** the preprocessing produced more than one variant (original + expanded or rewritten + expanded)
- **THEN** the system SHALL run retrieval per variant and merge results using reciprocal-rank fusion
- **AND** duplicates SHALL be collapsed by document id

#### Scenario: Single variant

- **WHEN** only one variant is available
- **THEN** fusion SHALL be a no-op and the result SHALL be the single retrieval output

### Requirement: Cold-start fallback

The system SHALL produce at least `TOP_K` results when the collection is non-empty, even if individual variants return fewer.

#### Scenario: Sparse variant results

- **WHEN** the fused result count is below `TOP_K`
- **THEN** the system SHALL run an additional retrieval pass with the rewritten query
- **AND** the additional results SHALL be merged by document id with the existing fused set

### Requirement: Existing-index bootstrap

The system SHALL initialize the retrieval index from the persisted collection on first use without re-embedding existing documents.

#### Scenario: First query of a session

- **WHEN** the retrieval subsystem is constructed at process start
- **THEN** it SHALL load the index from the existing collection
- **AND** it SHALL NOT re-read or re-embed any document
