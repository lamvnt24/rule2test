.PHONY: demo check test seed reset import-demo quality-gate benchmarks ai-doctor

PY = py -3 -B

demo:
	$(PY) scripts/run_demo.py --seed

check:
	$(PY) scripts/run_demo.py --check

test:
	$(PY) -m unittest discover -s tests -v

seed:
	$(PY) scripts/seed_demo.py

reset:
	$(PY) scripts/reset_demo.py

import-demo:
	$(PY) scripts/run_import_demo.py

quality-gate:
	$(PY) scripts/evaluate_quality_gate.py

benchmarks:
	$(PY) scripts/collect_benchmarks.py

ai-doctor:
	$(PY) scripts/ai_doctor.py
