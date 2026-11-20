PYTHON ?= python3
PORT ?= 5000
BOARD ?= 5v16

.PHONY: run stop status setup tools recover test help

help:
	@echo 'make run     Lancer en arrière-plan sur http://127.0.0.1:$(PORT)'
	@echo 'make stop    Arrêter la web app'
	@echo 'make status  Afficher son état'
	@echo 'make tools   Installer Arduino CLI et les cartes (Internet requis)'
	@echo 'make recover Récupérer une carte via RESET (BOARD=5v16 ou 3v8)'
	@echo 'make test    Exécuter les tests Python'

.venv/.installed: requirements.txt
	$(PYTHON) -m venv .venv
	.venv/bin/python -m pip install -r requirements.txt
	@touch $@

setup: .venv/.installed

run: setup
	@.venv/bin/python scripts/service.py start --port $(PORT)

stop:
	@$(PYTHON) scripts/service.py stop

status:
	@$(PYTHON) scripts/service.py status

tools: setup
	@.venv/bin/python scripts/install_tools.py

recover: setup
	@.venv/bin/python scripts/recover.py --board $(BOARD)

test: setup
	@.venv/bin/python -m unittest discover -s tests -v
	@if command -v node >/dev/null 2>&1; then node tests/password_generator.test.mjs; else echo 'Node absent : tests du générateur ignorés (application utilisable sans Node).'; fi
