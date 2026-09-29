# Every target delegates to scripts/task.py so make, pnpm and the shell scripts all execute the
# same cross-platform implementation. `make` itself is optional: `pnpm dev` works without it.
SHELL := /bin/bash
PYTHON ?= $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null)

.PHONY: install dev test lint build clean help

help:
	@$(PYTHON) scripts/task.py --help

install:
	$(PYTHON) scripts/task.py setup

dev:
	$(PYTHON) scripts/task.py dev

test:
	$(PYTHON) scripts/task.py test

lint:
	$(PYTHON) scripts/task.py lint

build:
	$(PYTHON) scripts/task.py build

clean:
	$(PYTHON) scripts/task.py clean
