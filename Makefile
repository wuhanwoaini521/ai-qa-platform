.PHONY: dev test lint build clean install

install:
	mise install
	uv sync --all-packages
	pnpm install

dev:
	./scripts/dev

test:
	./scripts/test

lint:
	./scripts/lint

build:
	pnpm --filter @ai-qa/web build

clean:
	rm -rf .venv node_modules apps/web/node_modules apps/web/dist runtime/ai_qa_platform.db
