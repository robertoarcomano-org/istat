VENV   := .venv
PYTHON := $(VENV)/bin/python
STAMP  := $(VENV)/.requirements-installed
DB     ?= employment.sqlite

.PHONY: all init download export clean

all: init download export

# crea il python env e installa le dipendenze (rifatto solo se cambia requirements.txt)
init: $(STAMP)

$(STAMP): requirements.txt
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install -r requirements.txt
	touch $@

# scarica da Istat struttura e dati (salta i file già presenti)
download: $(STAMP)
	$(PYTHON) -c "from istat import Istat; Istat()"

# carica i dati scaricati nel db sqlite ($(DB))
export: download
	$(PYTHON) -c "from istat import Istat; Istat().export_db(\"$(DB)\")"

# cancella dati scaricati, db e cache; il python env ($(VENV)) resta
clean:
	rm -f employment_*_structure.xml employment_*_data.xml $(DB) superficie.html dl.log
	rm -rf __pycache__ tests/__pycache__ .pytest_cache
