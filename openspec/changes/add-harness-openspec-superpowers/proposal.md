# Add Harness + OpenSpec + Superpowers 工程化升级

## Why

当前 Agentic-RAG-demo 代码质量不错，但工程化程度不足：

- **无依赖声明**：没有 `pyproject.toml` / `requirements.txt`，新环境搭建靠 README 手动 pip install
- **零测试**：核心 RAG 流水线（预处理 → 召回 → 后处理 → 生成）没有任何自动化测试保障
- **无 CI**：没有自动化检查，代码质量依赖人肉 review
- **规格缺失**：README 引用了 `docs/changes/`、`docs/specs/`、`.claude/rules/core-rules.md`，但文件全都不存在
- **无智能体工作流**：没有给 AI 编程助手定义行为规则和工作方法论

这三个缺口分别对应三个互补的开发理念：

| 理念 | 解决什么 | 类比 |
|------|---------|------|
| **Harness** | 提供执行基础设施（测试、CI、lint） | 肌肉 |
| **OpenSpec** | 定义"做什么"（需求 → 规格 → 变更） | 大脑 |
| **Superpowers** | 定义"怎么做"（方法论 → 技能 → 工作流） | 方法 |

## What Changes

### 1. Harness：工程基座

- 添加 `pyproject.toml`（依赖声明 + pytest/ruff/mypy 配置）
- 添加 `Makefile`（统一任务入口：`make test` / `make lint` / `make run`）
- 添加 `tests/` 目录（unit + integration 两层，mock 外部依赖）
- 添加 `.github/workflows/ci.yml`（lint → type-check → test）
- 添加 `.pre-commit-config.yaml`（本地提交前自动检查）

### 2. OpenSpec：规格驱动

- 建立 `openspec/` 标准目录结构
- 编写已部署能力的规格文档（`openspec/specs/`）
- 创建本次变更提案（`openspec/changes/add-harness-openspec-superpowers/`）
- 添加 `openspec/config.yaml` 项目上下文配置

### 3. Superpowers：智能体方法论

- 创建 `AGENTS.md`（agents.md 通用标准，替代 Claude Code 专属的 CLAUDE.md，行为规则直接内含）

### 4. 集成

- 更新 `README.md`（反映新目录结构 + 贡献流程）
- 统一所有文档引用路径，消灭悬空引用

## Capabilities

### New Capabilities

- `engineering-harness`：测试、CI、lint 等工程基础设施
- `spec-driven-development`：OpenSpec 规格驱动开发流程
- `agent-methodology`：AI 智能体行为规则与工作流

### Modified Capabilities

- `api-contract`：无变更，仅补充规格文档
- `rag-pipeline`：无变更，仅补充规格文档

## Impact

- **新增文件**：~25 个（配置、测试、规格、规则）
- **修改文件**：`README.md`、`AGENTS.md`
- **不修改**：`app/` 下任何业务代码（这次只补基础设施，不动逻辑）
- **风险**：低——全部是新增，不影响现有功能
