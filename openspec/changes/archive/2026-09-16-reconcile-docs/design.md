# 设计:文档对齐

## 背景

文档一致性问题的根因不是"谁写错了",而是"没有 source-of-truth 约定" — 三份文档平级存在,各自独立维护,漂移是必然。本次工作不止"改对这三份",还要把"哪份该信什么"这件事**写进**约定本身,让以后不再漂移。

## 决策

### 选 `CLAUDE.md` 当唯一真相源

理由:
1. **CLAUDE.md 在 Claude Code 的项目指令链路里有最高优先级** — 它加载到每次会话的系统提示里,Claude 实际工作时只能看到它
2. **README.md 是 GitHub 着陆页** — 访客(可能是非 Claude 的 AI、可能是人)需要的是 30 秒能读完的 quickstart,不是真相源
3. **需求文档.md 是历史快照** — 它记录的是"立项时怎么想的",代码已经迭代多轮,它的口径不可能再追上

因此:
- CLAUDE.md:**全部事实口径写齐**(段数、阈值、路径、模型名、状态)
- README.md:**只讲快速开始 + 目录结构 + 贡献流程**,一切"为什么"指向 CLAUDE.md
- 需求文档.md:**归档,加封条**,绝不被引用为规范

### "OpenSpec 指针" 写进 CLAUDE.md

CLAUDE.md 末尾新增 §6 介绍 `openspec/` 目录结构 + 4 个动作 + spec.md 写法。这样:

- 以后任何改 app/ 的工作,Claude 第一反应是"先看 openspec/changes/ 有没有对应 change"
- 改动流程从"靠对话记忆"变成"看 proposal.md"
- "MinerU 开关在那摆着没人拨"这种悬空状态,变成"`openspec/changes/wire-mineru-pipeline/` 里有完整提案等你拍板"

### 不创建 `.claude/settings.json`

`.claude/settings.json` 一旦写错会影响所有 Claude Code 会话(包括不在本项目目录的)。本次工作的风险/收益不匹配 — 用 CLAUDE.md 已经能让"以后不再漂移"的 80% 目标达成,剩 20%(自动 hook)不值得冒险。

### spec.md 写法参考 obra/superpowers 的 OpenSpec conventions

参考 `https://github.com/Fission-AI/OpenSpec/blob/main/openspec/specs/openspec-conventions/spec.md`:

- `### Requirement` + `#### Scenario` 三/四 hash
- 场景用 `- **WHEN/THEN/AND**` 三段式
- 行为优先,**库名/类名放 design.md**
- 顶层能力目录用 kebab-case

## 预期 Diff 范围

`git status` 落盘后应显示:

```
M  CLAUDE.md                              # 重写
M  README.md                              # 精简
D  需求文档.md                              # git mv 到 docs/
?? CLAUDE.md                              # git 未追踪过(原本 untracked,被覆盖)
?? converted/                             # 已存在的空目录
?? docs/                                  # 新建(从根挪走的需求文档)
?? openspec/                              # 新建(脚手架 + 3 个 change)
```

加上**未提交的** `app/core/config.py`(`MINERU_*` 4 个开关,本次不动)。