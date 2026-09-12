.PHONY: run test seed import-demo

run:
	python -m factory.server

test:
	python -B -m unittest discover -s tests -v

seed:
	python -B scripts/seed_demo.py

import-demo:
	python -B scripts/run_import_demo.py
