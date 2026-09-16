# Answer Generation

把重排后的高质量片段拼成上下文,生成最终回答 + 来源。

## Requirements

### Requirement: Grounded answer

The system SHALL generate answers strictly from the provided context chunks.

#### Scenario: Information present

- **WHEN** the context chunks contain information sufficient to answer the question
- **THEN** the system SHALL cite at least one and at most three sources
- **AND** the answer SHALL be written in the same language as the user's question

#### Scenario: Information absent

- **WHEN** the context chunks do not contain information sufficient to answer the question
- **THEN** the system SHALL respond with a clear "no information" message
- **AND** the response SHALL NOT fabricate or hallucinate content from outside the provided context

#### Scenario: Empty context

- **WHEN** reranking returned no chunks
- **THEN** the system SHALL return the canned "no information" response
- **AND** the source list SHALL be empty

### Requirement: Source attribution

The system SHALL return a source list alongside every answer.

#### Scenario: Each source entry

- **WHEN** a chunk is cited
- **THEN** the corresponding source entry SHALL contain: a 1-based index, a content preview, the relevance score (rounded to 4 decimal places), and the originating filename

### Requirement: No-fabrication contract

The system prompt SHALL explicitly forbid fabricating information not present in the supplied context.

#### Scenario: System prompt enforcement

- **WHEN** the LLM is invoked for answer generation
- **THEN** the system message SHALL include a clause prohibiting fabrication
- **AND** this clause SHALL NOT be user-overridable through the question field
