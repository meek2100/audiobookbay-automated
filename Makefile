run:
	source .venv/bin/activate && python3 app/app.py

venv:
	python3 -m venv .venv

# Modern install: Installs deps AND the app in editable mode
install:
	source .venv/bin/activate && pip install -e ".[dev]"

# Legacy compatibility if you still type 'make requirements'
requirements: install
