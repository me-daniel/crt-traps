# make: build main.pdf with tectonic. make refs: pull refs.bib from Zotero (ZOTERO_* names in .env.example).
main.pdf: main.tex refs.bib $(wildcard sections/*.tex generated/* figures/*)
	tectonic -X compile main.tex

refs:
	python3 -I ../.claude/skills/zoterofy/zotero.py pull refs.bib --ledger ../sources.md

.PHONY: refs
