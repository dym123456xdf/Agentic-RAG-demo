# Reranking

在向量召回之上做精排,把真正相关的片段顶到前面。

## Requirements

### Requirement: Distance-based pre-filter

The system SHALL drop retrieved chunks whose Milvus cosine distance exceeds `SIMILARITY_CUTOFF` before reranking.

#### Scenario: Default cutoff accepts everything

- **WHEN** `SIMILARITY_CUTOFF` is 2.0 (the upper bound of cosine distance)
- **THEN** no chunk SHALL be dropped by the pre-filter
- **AND** reranking SHALL operate on the full retrieved set

#### Scenario: Tightened cutoff drops noise

- **WHEN** `SIMILARITY_CUTOFF` is reduced below the typical noise floor
- **THEN** chunks with distance above the cutoff SHALL be excluded from reranking

### Requirement: Cross-encoder reranking

The system SHALL rerank the surviving chunks using a cross-encoder model and return the top `RERANK_TOP_N` by descending reranker score.

#### Scenario: Default reranker

- **WHEN** reranking runs with default config
- **THEN** the system SHALL use `BAAI/bge-reranker-v2-m3`
- **AND** the device SHALL be MPS if available, otherwise CPU

#### Scenario: Score overwrite

- **WHEN** reranking completes
- **THEN** each surviving chunk SHALL carry the reranker score as its `score` field (not the original cosine distance)

### Requirement: Deterministic top-N

The system SHALL return chunks in stable descending order of reranker score, with ties broken by original retrieval rank.

#### Scenario: Equal scores

- **WHEN** two chunks receive the same reranker score
- **THEN** the chunk ranked higher in the original retrieval SHALL appear first

### Requirement: Empty-input handling

The system SHALL return an empty list when the pre-filter removes all chunks.

#### Scenario: All chunks filtered out

- **WHEN** no chunk passes the distance cutoff
- **THEN** the system SHALL return an empty list
- **AND** downstream stages SHALL handle this gracefully (the answer generator SHALL return a "no information" canned response)
