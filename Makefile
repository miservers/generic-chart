PYTHON ?= python3

.PHONY: check
check:
	$(PYTHON) tests/check.py
