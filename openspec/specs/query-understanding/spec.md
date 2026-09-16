# Query Understanding

把用户原始问题加工成"更适合检索"的形式,并提供调试元数据。

## Requirements

### Requirement: Multi-turn query rewriting

The system SHALL rewrite the current question into a self-contained, de-referenced query using the most recent turns of conversation history.

#### Scenario: No history

- **WHEN** the request carries no prior conversation turns
- **THEN** the rewritten query SHALL equal the original query verbatim
- **AND** no rewriting call SHALL be issued

#### Scenario: With history

- **WHEN** the request carries prior conversation turns
- **THEN** the rewritten query SHALL replace pronouns, omitted subjects, and other anaphoric references with their referents from prior turns
- **AND** only the last 6 messages (3 turns) of history SHALL be considered

### Requirement: Intent classification

The system SHALL classify every user question into exactly one of `factual`, `explanatory`, `comparison`, `creative`, or `chitchat`.

#### Scenario: Default classification

- **WHEN** the classification result is ambiguous or unparseable
- **THEN** the system SHALL default to `factual`

### Requirement: Query expansion

The system SHALL produce up to 3 semantically related reformulations of the rewritten query.

#### Scenario: Expansion produces variants

- **WHEN** the rewritten query is expandable
- **THEN** the system SHALL return 1 to 3 distinct variants
- **AND** each variant SHALL be a complete, grammatically valid question

#### Scenario: Empty expansion fallback

- **WHEN** the expansion step yields no usable variants
- **THEN** the system SHALL fall back to a single-item list containing the rewritten query

### Requirement: Single-call preprocessing

The system SHALL complete rewriting, intent classification, and expansion using a fixed number of LLM calls per query (at most 3), independent of conversation length.

#### Scenario: History length scaling

- **WHEN** the conversation history grows from 1 to 100 turns
- **THEN** the number of LLM calls per preprocessing SHALL NOT increase

### Requirement: Preprocessing artifact surface

The system SHALL expose the preprocessing result as a structured object containing `original`, `rewritten`, `expanded` (list of strings), and `intent`.

#### Scenario: Downstream consumers

- **WHEN** any downstream stage needs the rewriting or expansion
- **THEN** it SHALL read from this artifact rather than re-running preprocessing
