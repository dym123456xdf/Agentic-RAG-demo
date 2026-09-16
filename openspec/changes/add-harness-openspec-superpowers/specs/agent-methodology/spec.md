# agent-methodology 变更规格

## ADDED Requirements

### Requirement: 行为规则
项目 SHALL 提供 `AGENTS.md`(内含行为规则),约束 AI 编程助手行为。

#### Scenario: 规则可发现
- **WHEN** AI 助手进入项目
- **THEN** AGENTS.md 包含完整的行为规则(规格先行 / TDD / 验证优先等)
- **AND** 规则文档包含 TDD / 规格先行 / 验证优先等核心理念

### Requirement: 工作流定义
规则文档 SHALL 定义从提案 → 测试 → 实现 → 验证 → 提交的完整工作流。

#### Scenario: 非琐碎改动流程
- **GIVEN** AI 助手收到改动 app/ 下代码的请求
- **WHEN** 助手开始工作
- **THEN** 先检查 openspec/changes/ 是否已有提案
- **AND** 写测试后再写实现
- **AND** make check 通过后才提交
