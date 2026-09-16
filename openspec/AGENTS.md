# AGENTS.md — Claude 在 openspec/ 工作的指令

> 这是 Claude Code(以及任何 AI 助手)在 `openspec/` 目录工作时的指令文件。
> 根目录的 [CLAUDE.md](../CLAUDE.md) 是项目全局真相源;本文件专门约束 OpenSpec 工作流。

## 怎么用这套规范

**`specs/` 是当前已部署的能力**(永久,只增不改 — 改要通过 change → archive 流程)
**`changes/` 是进行中的变更提案**(临时,实现并 archive 后挪到 `changes/archive/`)
**两者关系**:`changes/<name>/specs/<capability>/spec.md` 描述 **未来状态**;archive 时合并进 `specs/<capability>/spec.md`,已部署规格继续反映"系统现在能做到什么"。

## 工作前必读

1. **读相关能力规格**:`specs/<capability>/spec.md` — 看当前契约是什么
2. **查相关 change**:`changes/*/proposal.md` — 看有没有正在做类似事,要不要合并
3. **不要直接改 specs/ 下的文件** — 改它意味着绕过了 change → archive 流程,审计链断了

## 改动流程(对应 OpenSpec 的 4 个动作)

| 动作 | 触发场景 | 你应该 |
|---|---|---|
| **explore** | 不确定要做什么 | 跟用户聊清楚需求边界 |
| **propose** | 知道要做但还没细化 | 写 `changes/<name>/{proposal,tasks,design}.md`(能力变化时加 `specs/`)|
| **apply** | 已批准要实施 | 按 `tasks.md` 改代码,保持 proposal 一致 |
| **archive** | 实施完 + 测试过 | 把 change 挪到 `changes/archive/`,把 `changes/<name>/specs/` 内容并入 `specs/` |

## spec.md 写法(强制)

````markdown
## (Optional) ADDED Requirements   ← 仅 changes/<name>/specs/ 下用,标"新增"

### Requirement: <动词短语,描述能力>
The system SHALL <可观测行为>.

#### Scenario: <短句>
- **WHEN** <触发条件>
- **THEN** <期望结果>
- **AND** <可选附加>
````

规则:
- 能力目录用 **kebab-case**
- `### Requirement` 用三 hash;`#### Scenario` 用四 hash
- 场景用 `- **WHEN/THEN/AND** ...` 三段式,至少 WHEN + THEN
- 行为优先,不写内部实现(库名/类名放 design.md)
- "SHALL" 用于强制约束;"SHALL NOT" 用于禁止;避免"should""may"这类弱词

## proposal.md 写法(强制)

每个 change 第一段必须是 **Why** — 一两句话说清问题根因,不要写解决方案。
**What Changes** 段列出:
- 新增 / 修改 / 删除的能力(对应 `specs/` 下的哪些目录)
- 影响范围(改哪些 app/ 文件)
- 不做什么(explicit non-goals)

## tasks.md 写法(强制)

checkbox 清单,数字编号(`- [ ] 1.1 ...`),对应 proposal 的 What Changes 段落。
每条任务颗粒度:几行代码 / 一个函数 / 一个测试。颗粒度过粗就拆。

## design.md 写法(可选但推荐)

技术取舍:为什么选 A 不选 B。OpenSpec 默认 schema 不强制,但本仓库约定:
- 涉及外部依赖 / 性能 / 安全取舍 → 必写
- 1-2 行能说清的 → 可省

## 验证(本仓库自定)

任何 change 的 `tasks.md` 末尾追加 "Verification" 段:
- 怎么手动验证(curl 命令、浏览器步骤)
- 跑哪些单元/集成测试(本仓库目前无测试,此段可写"无测试")