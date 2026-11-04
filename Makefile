PYTHON ?= .venv/bin/python
export MPLCONFIGDIR := $(CURDIR)/cache/matplotlib
export HF_HOME := $(CURDIR)/cache/huggingface
export OMP_NUM_THREADS := 8
export MKL_NUM_THREADS := 8

.PHONY: smoke train models e1 e2 e3 e4 pilot report
smoke:
	$(PYTHON) -m pytest -q tests
train:
	$(PYTHON) scripts/train_e1.py
models:
	$(PYTHON) scripts/prepare_models.py
e1: train
	$(PYTHON) -m src.runner e1 --resume
	$(MAKE) report
e2: models
	$(PYTHON) -m src.runner e2 --resume
	$(MAKE) report
e3:
	$(PYTHON) -m src.runner e3 --resume
	$(MAKE) report
e4:
	$(PYTHON) -m src.runner e4 --resume
	$(MAKE) report
pilot:
	$(MAKE) smoke
	$(MAKE) e1
	$(MAKE) e2
	$(MAKE) e3
	$(MAKE) e4
report:
	$(PYTHON) -m src.reporting
