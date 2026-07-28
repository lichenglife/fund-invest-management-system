# Makefile · FundLens 常用命令封装（对齐 CLAUDE.md §8）

.PHONY: install lint format typecheck test check run-api run-ui up down logs clean

install:
	pip install -r requirements.txt -r requirements-dev.txt

format:
	black . && isort .

lint:
	ruff check .

typecheck:
	mypy .

test:
	pytest --cov=domain --cov=schemas --cov=api --cov=infra --cov=config --cov-report=term-missing

# 全部门禁（本地一键）
check: lint typecheck test

run-api:
	uvicorn api.main:app --reload

run-ui:
	streamlit run app/app.py

# Docker
up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
