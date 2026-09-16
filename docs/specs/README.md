# specs/

已部署能力契约。

## 当前能力清单

| 能力 | spec 路径 | 状态 |
|---|---|---|
| (空) | — | 本次清理不强制建契约;按需后续补 |

## 何时新增

`app/` 下任何模块首次落地非琐碎能力前,在 `docs/specs/<capability>/spec.md` 写一份契约。模板:

- `### Requirement:<一句话>`
- `#### Scenario:<场景名>`
- **`WHEN`** `<条件>`
- **`THEN`** `<期望>`

详见 `core-rules.md`。
