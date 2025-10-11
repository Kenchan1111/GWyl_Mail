.PHONY: help install dev test lint format clean run-tests

help:
	@echo "GWyl Mail - Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  install     Install production dependencies"
	@echo "  dev         Install development dependencies"
	@echo "  test        Run tests with coverage"
	@echo "  lint        Run linters (ruff, mypy)"
	@echo "  format      Format code (black)"
	@echo "  clean       Clean build artifacts"
	@echo "  run-tests   Run specific test file (e.g., make run-tests TEST=test_canonical)"

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check gwyl_mail tests
	mypy gwyl_mail

format:
	black gwyl_mail tests

clean:
	rm -rf build/ dist/ *.egg-info
	rm -rf .pytest_cache .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

run-tests:
	pytest tests/$(TEST).py -v
