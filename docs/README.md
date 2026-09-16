# docs/

本目录承担原 `openspec/{specs,changes}/` 的职能:**已部署能力契约 + 进行中变更提案**。

## 子目录

| 目录 | 职能 | 何时新增 |
|---|---|---|
| `specs/` | 已部署能力契约(每个能力一个 `spec.md`,含 `### Requirement` 与 `#### Scenario`) | 能力首次落地后;改 `app/` 任何文件前应确认对应 spec 存在 |
| `changes/` | 进行中的变更提案(每个提案一个 `<name>/` 子目录,含 `proposal.md` + `tasks.md` + 可选 `specs/<capability>/spec.md`) | 非琐碎改动前;改 `app/` 任何文件前先看 `docs/changes/` 下是否有相关 proposal |

## 流程

1. 读 `docs/specs/` 下相关契约,看是否已有
2. 没有则在 `docs/changes/<name>/` 建新提案(`proposal.md` + `tasks.md`)
3. 改完代码,在 `docs/changes/<name>/specs/<capability>/spec.md` 写 future-state 规格(若能力有变)
4. 完成后合并到 main,提案目录保留作为历史(无 archive 工具)

详见 `core-rules.md`。