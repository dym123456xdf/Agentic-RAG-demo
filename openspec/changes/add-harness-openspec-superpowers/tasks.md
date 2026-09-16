## 1. Harness 工程基座

- [x] 1.1 创建 `pyproject.toml`（依赖声明 + pytest/ruff/mypy 配置）
- [x] 1.2 创建 `Makefile`（test / lint / format / run / ingest 任务入口）
- [x] 1.3 创建 `tests/conftest.py`（mock LLM / Mock Milvus / Mock Embedding fixtures）
- [x] 1.4 编写单元测试：`test_pre_query.py` `test_post.py` `test_splitter.py` `test_generator.py`
- [x] 1.5 编写集成测试：`test_api.py`（/chat /upload 端点）
- [x] 1.6 创建 `.github/workflows/ci.yml`（lint → type-check → test）
- [x] 1.7 创建 `.pre-commit-config.yaml`

## 2. OpenSpec 规格驱动

- [x] 2.1 创建 `openspec/config.yaml`（项目上下文 + rules）
- [x] 2.2 编写已部署能力规格：`openspec/specs/rag-pipeline/spec.md`
- [x] 2.3 编写已部署能力规格：`openspec/specs/document-ingestion/spec.md`
- [x] 2.4 编写已部署能力规格：`openspec/specs/api-contract/spec.md`
- [x] 2.5 编写本次变更规格增量：`openspec/changes/.../specs/` 下 3 个能力

## 3. Superpowers 智能体方法论

- [x] 3.1 将行为规则合并进 `AGENTS.md`（TDD / 规格先行 / 验证优先）
- [x] 3.2 创建 `AGENTS.md`（指向正确路径 + 工作流说明）

## 4. 集成与文档

- [x] 4.1 更新 `README.md`（新目录结构 + 贡献流程）
- [x] 4.2 验证：`make lint` 通过
- [x] 4.3 验证：`make test` 通过
