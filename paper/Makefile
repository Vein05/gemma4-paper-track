# The paper. writeup.md is the canonical text (pasted into the Kaggle Writeup as is); rubber-stamp.pdf is the same
# text in the preprint layout (ICLR style file for format only); rubber-stamp-supplement.pdf holds the supplement.
# make            -> references from references.bib, prose check, word count, both PDFs
# Figures: `make export` (Kaggle PNGs) and `make paper` (print PDFs) in ../../figures/gemma4-rubber-stamp/.
PROSE = python3 ../../prose-check/prose_check.py --config prose-check.toml
TEX = TEXINPUTS=latex//: BSTINPUTS=latex//:

.PHONY: all refs check count clean

all: rubber-stamp.pdf rubber-stamp-supplement.pdf

refs:
	python3 latex/refs.py

check: refs
	@if [ -f ../../prose-check/prose_check.py ]; then $(PROSE) writeup.md latex/supplement/*.tex; \
	else echo "prose check skipped (research/prose-check is not part of this repository)"; fi

count: refs
	python3 latex/wordcount.py writeup.md

rubber-stamp.pdf: writeup.md latex/writeup.lua latex/header.tex figures/pdf/*.pdf check count
	$(TEX) pandoc writeup.md -f markdown-auto_identifiers --lua-filter latex/writeup.lua -H latex/header.tex \
	  --pdf-engine=pdflatex -V documentclass=article -V fontsize=10pt -V colorlinks=true -V linkcolor=Maroon -V urlcolor=NavyBlue -o $@

rubber-stamp-supplement.pdf: latex/supplement/*.tex figures/pdf/*.pdf check
	cd latex/supplement && TEXINPUTS=..//: pdflatex -interaction=nonstopmode supplement > /dev/null; \
	  TEXINPUTS=..//: pdflatex -interaction=nonstopmode supplement | grep -E "Error|Output written|Overfull"; true
	cp latex/supplement/supplement.pdf $@

clean:
	rm -f latex/supplement/*.aux latex/supplement/*.log latex/supplement/*.out
