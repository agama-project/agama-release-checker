MAIN = .
check: check-black check-mypy check-pytest
check-black:
	black --diff --check ${MAIN}
check-mypy:
	mypy ${MAIN}
check-pytest:
	PYTHONPATH=src pytest --cov --cov-report=term --cov-report=html tests/
check-pytest-nocov:
	PYTHONPATH=src pytest tests/

.PHONY: docs
docs:
	PYTHONPATH=src uv run --with pdoc pdoc agama_release_checker -o docs/
