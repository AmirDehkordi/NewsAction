# NewsAction standard commands (CLAUDE.md "Standard commands").
UV ?= $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)
RUN := $(UV) run --locked
PY_DIRS := src tests scripts

.PHONY: sync lint format type test manifest manifest-deep ledgers verify paper paper-preview paper-text paper-pdf

sync:            ## install the locked environment
	$(UV) sync --locked

lint:            ## ruff check + format check
	$(RUN) ruff check $(PY_DIRS)
	$(RUN) ruff format --check $(PY_DIRS)

format:          ## apply ruff formatting and safe fixes
	$(RUN) ruff format $(PY_DIRS)
	$(RUN) ruff check --fix $(PY_DIRS)

type:            ## mypy --strict on the package
	$(RUN) mypy --strict src/

test:            ## fast tests, no network
	$(RUN) pytest -q -m "not network"

manifest:        ## re-hash every work/ artifact; check Data/ inputs (size+mtime) and docs/DATA_CONTRACT.md
	$(RUN) python -m newsaction.io check

manifest-deep:   ## as manifest, and re-hash every Data/ input
	$(RUN) python -m newsaction.io check --deep

ledgers:         ## verify the hash chain of every ledgers/*.jsonl
	$(RUN) python -m newsaction.ledger check

verify: lint type test manifest ledgers

paper:           ## NA-14: rebuild every paper table, figure CSV, figure and caption offline; check the committed digests
	$(RUN) python -m newsaction.figures.paper

paper-preview:   ## NA-14: compile artifacts/NA-14/paper_preview.tex with tectonic; check errors, overfull boxes, fonts
	$(RUN) python -m newsaction.figures.preview --compile

paper-text:      ## NA-16: write paper/generated/numbers.tex and arxiv/abstract.txt from NA-14's keys; check the sources
	$(RUN) python -m newsaction.paper.numbers

paper-pdf: paper-text  ## NA-16: compile paper/main.tex with tectonic (--keep-logs) and check the log and the PDF
	$(RUN) python -m newsaction.paper.build
