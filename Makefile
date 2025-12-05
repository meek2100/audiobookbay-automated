run:
	.venv/bin/python -m app.app

venv:
	python3 -m venv .venv

# Modern install: Installs deps AND the app in editable mode
install:
	.venv/bin/pip install -e ".[dev]"
