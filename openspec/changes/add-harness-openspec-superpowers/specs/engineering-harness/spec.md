# engineering-harness 变更规格

## ADDED Requirements

### Requirement: 依赖声明
项目 SHALL 通过 `pyproject.toml` 声明运行时依赖和开发依赖。

#### Scenario: 新环境安装
- **WHEN** 执行 `pip install -e ".[dev]"`
- **THEN** 安装运行时依赖 + 开发工具

### Requirement: 统一任务入口
项目 SHALL 提供 Makefile,支持 `make test` / `make lint` / `make check` / `make run`。

#### Scenario: 一键检查
- **WHEN** 执行 `make check`
- **THEN** 依次运行 lint → typecheck → test
- **AND** 任一步骤失败即非零退出

### Requirement: 单元测试
项目 SHALL 为 app/rag/ 下的核心模块提供单元测试,mock 所有外部依赖。

#### Scenario: 无外部依赖运行
- **GIVEN** 没有 Milvus 实例 / LLM API key
- **WHEN** 执行 `make test`
- **THEN** 所有单元测试通过

### Requirement: CI
项目 SHALL 提供 GitHub Actions workflow,在 push / PR 时自动运行 lint + test。
