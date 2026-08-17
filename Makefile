PYTHON ?= python3
export PYTHONPATH := src

.PHONY: validate test schema demo compile clean

validate: compile test schema demo

test:
	$(PYTHON) -m unittest discover -s tests -v

schema:
	$(PYTHON) scripts/validate_schemas.py

compile:
	$(PYTHON) -m compileall -q src tests scripts

demo:
	$(PYTHON) -m acceptance_lab demo --workspace .demo

clean:
	rm -rf .demo .acceptance-lab build dist *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
