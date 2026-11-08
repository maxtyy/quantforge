.PHONY: install test lint demo serve build
install:
	python -m pip install -e '.[dev]'
test:
	pytest -q
lint:
	ruff check .
	ruff format --check .
demo:
	quantforge demo
serve:
	quantforge serve
build:
	python -m build
