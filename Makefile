# make: rerun both analyses from runs/, redraw the figures, build paper/main.pdf. No model calls.
# make items: regenerate experiments/*.yaml from the item generators.
PY = uv run python

all: tables figures
	$(MAKE) -C paper

tables:
	$(PY) experiments/crt-b.py > /dev/null
	$(PY) experiments/crt-a.py > /dev/null

figures:
	$(PY) experiments/crt-concept.py
	$(PY) experiments/crt-figures.py
	$(PY) experiments/crt-graphs.py
	pdftoppm -png -r 150 -singlefile paper/figures/fig-results.pdf paper/figures/fig-results  # README image (poppler)
	pdftoppm -png -r 150 -singlefile paper/figures/fig-results.pdf paper/figures/fig-results

items:
	$(PY) experiments/make-crt-pairs.py
	$(PY) experiments/make-crt-b.py
	$(PY) experiments/make-crt-a.py

.PHONY: all tables figures items
