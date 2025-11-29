.PHONY: test package

test:
	@echo "Running code quality checks and tests..."
	ruff check .
	black --check .
	mypy .
	pytest -q

package:
	@echo "Packaging Kairoscope artifacts..."
	python -m kairoscope.cli export
