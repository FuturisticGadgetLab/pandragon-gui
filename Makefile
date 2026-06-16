# Pandragon GUI. Development and runtime automation
#
# Usage:
#   make              # default: run
#   make run          # launch GUI
#   make venv         # create venv + install deps
#   make deps         # re-install deps
#   make clean        # remove venv + artifacts

PYTHON = python3
VENV = venv
PIP = $(VENV)/bin/pip

.PHONY: default run venv deps clean

default: run

venv:
	@test -d $(VENV) || (echo "[*] Creating GUI venv..." && $(PYTHON) -m venv $(VENV))
	@echo "[*] Upgrading pip/setuptools/wheel..."
	@$(PIP) install --upgrade pip setuptools wheel -q
	@echo "[*] Installing GUI dependencies..."
	@$(PIP) install -r requirements.txt
	@if [ -d ../tools ]; then \
		echo "[*] Installing pandragon-config-builder from ../tools..."; \
		$(PIP) install -e ../tools; \
	fi
	@echo "[+] GUI venv ready"

deps: venv
	@echo "[*] Re-installing GUI dependencies..."
	@$(PIP) install -r requirements.txt
	@echo "[+] Done"

run: venv
	@echo "[*] Starting Pandragon GUI..."
	@$(VENV)/bin/python run_gui.py

clean:
	rm -rf $(VENV)
	find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	rm -f *.log
	@echo "[+] GUI clean complete"
