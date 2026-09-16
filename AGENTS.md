# AGENTS.md

> 本文件遵循 [agents.md](https://agents.md) 通用标准,Codex / Cursor / Devin / Copilot 等 AI 编程助手会自动读取。

5 段模块化 RAG 流水线:查询预处理 → 向量召回 → 后处理 → 答案生成。
入口 `main.py`,Python ≥ 3.11。

---

## 行为规则

> 这些规则约束所有 AI 编程助手在此项目中的行为。不是建议,是必须遵守的规范。

### 1. 规格先行(OpenSpec 理念)

任何非琐碎改动(改 `app/` 下的代码、加接口、调整流水线结构),必须先走 OpenSpec 流程:

1. **查重**:看 `openspec/changes/` 下是否已有相关提案
2. **立项**:没有则创建 `openspec/changes/<change-name>/proposal.md`
   - `## Why` — 为什么做(1-3 段)
   - `## What Changes` — 做什么(编号列表)
   - `## Impact` — 影响面(哪些文件 / 风险等级)
3. **拆任务**:写 `tasks.md`(每个任务 2-5 分钟粒度,含验证步骤)
4. **写增量规格**:能力有变时,在 `openspec/changes/<name>/specs/<capability>/spec.md` 写 WHEN/THEN 场景

**禁止**:不写 proposal 就直接改业务代码。
**例外**:fix typo、调 log、改注释等不动逻辑的操作可以直接做。

### 2. TDD(Superpowers 理念)

写业务代码必须先写测试:

1. **RED**:写一个会失败的测试
2. **GREEN**:写最小实现让测试通过
3. **REFACTOR**:清理代码,测试仍绿

**测试规则**:
- 外部依赖(LLM / Milvus / Embedding / 文件系统)必须 mock
- 单元测试放 `tests/unit/`,集成测试放 `tests/integration/`
- 集成测试用 `@pytest.mark.integration` 标记
- 测试文件命名 `test_<module>.py`,测试类 `Test<Feature>`

### 3. 验证优先(Harness 理念)

不要"我觉得能跑"就说完成了。必须实际验证:

| 声明 | 验证命令 |
|------|---------|
| "测试通过" | `make test` 退出码 0 |
| "没有 lint 问题" | `make lint` 退出码 0 |
| "类型检查通过" | `make typecheck` 退出码 0 |
| "API 正常" | `uvicorn` 启动 + `curl` 验证 |

**提交前必须**:`make check` 全绿。

### 4. 模块边界

```
app/core/     ← 只做"配置 + 客户端封装",不写业务逻辑
app/rag/      ← 五段流水线,每段一个文件,职责单一
app/api/      ← FastAPI 路由,只做"接收请求 → 调 pipeline → 返回响应"
```

**禁止**:
- 在 `app/api/` 里写 RAG 逻辑
- 在 `app/rag/` 里直接读 `.env`
- 绕过 `Config` 类直接 `os.getenv()`

### 5. 提交规范

每完成一个 task 就提交一次,格式:`<type>(<scope>): <描述>`

- 类型:feat / fix / refactor / test / docs / chore
- 范围:rag / api / core / harness / spec
- 示例:`feat(rag): 添加查询扩展去重逻辑`

### 6. 文档一致性

改了接口 / 配置 / 目录结构,必须同步更新:
- [ ] `openspec/specs/` 对应能力规格
- [ ] `README.md`(如果影响快速开始 / 目录结构)
- [ ] `AGENTS.md`(如果影响 AI 助手工作流)

---

## 快速参考

```bash
make install  # 安装依赖
make test     # 跑单元测试
make check    # lint + typecheck + test
make run      # 启动服务
```

## 改动流程

1. 非琐碎改动 → 先建 `openspec/changes/<name>/proposal.md`
2. 写测试(RED) → 写实现(GREEN) → 重构(REFACTOR)
3. `make check` 全绿 → 提交

## 目录约定

```
openspec/           规格驱动(已部署能力 + 变更提案)
tests/              单元测试 + 集成测试
app/                业务代码(core / rag / api)
```

## 环境变量

根目录 `.env`(见 `.env.bak` 模板),必填:
- `MINIMAX_API_KEY` — LLM + Embedding API key
- `MINIMAX_GROUP_ID` — embedding 必填(MiniMax 私有协议)

可选:
- `MILVUS_URI` — 默认 `http://localhost:19530`
- `TOP_K` — 召回条数,默认 10
- `RERANK_TOP_N` — 重排后保留条数,默认 5
- `MINERU_ENABLED` — PDF 解析开关,默认 false
