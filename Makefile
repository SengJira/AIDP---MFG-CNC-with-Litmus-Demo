SHELL := /bin/bash
export PYSPARK_PYTHON := python3
export PYSPARK_DRIVER_PYTHON := python3

.PHONY: demo-setup demo-reset test dashboard offline multisource-setup multisource-test multisource-dashboard multisource-offline

demo-setup:
	python3 scripts/generate_synthetic.py
	python3 scripts/land_data.py
	python3 scripts/seed_label_bank.py
	python3 scripts/index_knowledge.py
	python3 jobs/detect.py --equipment-id CNC-01 --run-id cnc01_baseline
	python3 jobs/detect.py --equipment-id CNC-02 --run-id cnc02_unseeded
	python3 jobs/detect.py --equipment-id CNC-02 --run-id cnc02_seeded --seed-session cnc01_baseline

demo-reset:
	python3 scripts/reset_demo.py

test:
	python3 -m pytest -q

dashboard:
	streamlit run app/dashboard.py

offline:
	OFFLINE_MODE=1 streamlit run app/dashboard.py

multisource-setup:
	python3 scripts/load_multisource.py
	python3 scripts/create_analytics_views.py

multisource-test:
	python3 -m pytest tests/test_multisource.py -q

multisource-dashboard:
	streamlit run app/multisource_dashboard.py

multisource-offline:
	OFFLINE_MODE=1 streamlit run app/multisource_dashboard.py
