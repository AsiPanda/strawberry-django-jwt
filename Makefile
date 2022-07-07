.PHONY: test

test:
	poetry run mypy .
	poetry run pytest --cov-report=xml
