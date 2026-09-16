# spec-driven-development 变更规格

## ADDED Requirements

### Requirement: 规格目录结构
项目 SHALL 使用 `openspec/` 标准目录结构存放规格和变更提案。

#### Scenario: 目录结构
- **WHEN** 查看项目根目录
- **THEN** 存在 openspec/config.yaml
- **AND** 存在 openspec/specs/ 下按能力分目录的 spec.md
- **AND** 存在 openspec/changes/ 下按变更名分目录的 proposal.md + tasks.md

### Requirement: 已部署能力规格
项目 SHALL 为 rag-pipeline / document-ingestion / api-contract / query-processing 四个能力编写规格文档。

#### Scenario: 规格可追溯
- **WHEN** 查看任一能力的 spec.md
- **THEN** 包含 Purpose / Requirements / Scenario 结构
- **AND** 场景使用 WHEN/THEN 或 GIVEN/WHEN/THEN 格式

### Requirement: 变更提案
项目 SHALL 在 `openspec/changes/` 下存放进行中的变更提案。

#### Scenario: 提案结构
- **WHEN** 查看任一变更目录
- **THEN** 至少包含 proposal.md(Why / What Changes / Impact)
- **AND** 至少包含 tasks.md(编号任务列表)
