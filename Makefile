.PHONY: help install test lint format typecheck check run ci clean

PYTHON ?= python3
PIP ?= $(PYTHON) -m pip

help: ## 显示所有可用命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## 安装所有依赖（含 dev）
	$(PIP) install -e ".[dev]"

test: ## 运行全部测试
	$(PYTHON) -m pytest tests/ -m "not integration"

test-all: ## 运行全部测试（含集成，需要 Milvus）
	$(PYTHON) -m pytest tests/

coverage: ## 运行测试并生成覆盖率报告
	$(PYTHON) -m pytest tests/ -m "not integration" --cov=app --cov-report=term-missing

lint: ## 代码风格检查
	$(PYTHON) -m ruff check app/ tests/

format: ## 自动格式化代码
	$(PYTHON) -m ruff check --fix app/ tests/
	$(PYTHON) -m ruff format app/ tests/

typecheck: ## 类型检查
	$(PYTHON) -m mypy app/ --ignore-missing-imports

check: lint typecheck test ## 一次性跑 lint + typecheck + test（等同于 CI）

ci: check ## CI 入口（跟 GitHub Actions 保持一致）

run: ## 启动开发服务器
	$(PYTHON) -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

clean: ## 清理缓存和构建产物
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
