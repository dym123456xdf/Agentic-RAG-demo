# 文档对齐

## Why

仓库里有三份描述同一个系统的事实文档 — `CLAUDE.md`、`README.md`、`需求文档.md` — 它们对**同一件事**给出了不同答案:

| 维度 | CLAUDE.md | README.md | 需求文档.md |
|---|---|---|---|
| 流水线段数 | 5 段 | 4 段 | 5 段 |
| `SIMILARITY_CUTOFF` 默认值 | 2.0 | (未提) | 0.2 |
| 上传路径 | `/upload/files` | `/upload` | (未提) |
| MinerU 状态 | "开关已加,loader 未接通" | 未提 | 未提 |

AI 助手(以及任何按这三份文档行事的人)在做决策前必须先消歧,而消歧需要重新读代码 — 等于让规范文档**反向依赖**代码而不是反过来。代码才是真相源,文档本应是它的人工可读投影,不是它的平级副本。

## What Changes

把三份文档收敛到事实口径一致:

- **`CLAUDE.md`**:重写为 Claude Code 工作的唯一真相源。流水线段数 5 段、阈值 2.0、上传路径 `/upload/files`、MinerU 状态明确指向 `openspec/changes/wire-mineru-pipeline/`。新增 §6 "变更规范 (OpenSpec)" 章节。
- **`README.md`**:精简,只讲人话给 GitHub 访客。架构细节 / 模块边界 / 阈值等全部指向 CLAUDE.md。补充"贡献流程"段指向 `openspec/`。
- **`需求文档.md`**:`git mv` 到 `docs/requirements-archive.md`,文件顶部加 HTML 注释标注"已归档,以 CLAUDE.md 为准"。**不改内容**(它是历史快照)。

**新增 OpenSpec 脚手架**:`openspec/AGENTS.md`、`openspec/project.md`、`openspec/specs/<6 个能力>/spec.md`、`openspec/changes/<3 个未实施变更>/`。这是本次工作的"轨道",与文档收敛同次交付。

**影响范围**:
- 修改:`CLAUDE.md`、`README.md`(只动内容,不动 API / 配置 / 行为)
- 删除(并迁移):仓库根 `需求文档.md`
- 新建:`docs/requirements-archive.md`、`openspec/` 下全部
- **不动**:`app/` 下所有代码、`main.py`、`.env*`、`.gitignore`、`converted/`、`uploads/`、`static/`、`data/`

## Non-Goals

- **不修复**文档里点出来的几个真实 bug(`MILVUS_DB` 未生效、`processed.original` 喂 fuser) — 它们各自有独立的 OpenSpec change,本次只指向不修
- **不接通** MinerU 开关(只记录提案)
- **不引入**测试套件 / CI / lint(本仓库是 demo,CLAUDE.md §0 已声明)
- **不创建** `.claude/settings.json` 或 hooks(改所有会话行为的风险不值得为本次工作冒)

## Out of Scope

任何 OpenSpec `changes/` 下的 proposal(spec.md 改了的不算)— 本 change **不改任何能力规格**,只改文档。

## Success Criteria

1. 三份文档对"流水线段数 / 阈值 / 上传路径 / MinerU 状态"四个事实口径一致
2. `git log --follow docs/requirements-archive.md` 能追溯到 `需求文档.md` 的提交历史
3. `openspec/changes/` 下三个未实施 change 都有完整的 proposal/tasks/design.md,人工接手时不需要再问"为什么"