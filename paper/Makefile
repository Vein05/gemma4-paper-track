# The paper. writeup.md is the canonical text (its body goes into the Kaggle Writeup through submission.txt);
# rubber-stamp.pdf is the same
# text in the report layout (latex/rubberstamp.sty, latex/report-template.tex, latex/report.lua,
# latex/postprocess.py); rubber-stamp-supplement.pdf
# holds the supplement (latex/supplement/supplement.tex, same style, marks from latex/style_supplement.py).
# make            -> references from references.bib, prose check, word count, both PDFs, submission.txt
#                    (the Kaggle Writeup form, latex/submission.py)
# Figures: `make export` (Kaggle PNGs) and `make paper` (print PDFs) in ../../figures/gemma4-rubber-stamp/.
PROSE = prose-check --config prose-check.toml
TEX = TEXINPUTS=latex//: BSTINPUTS=latex//:

.PHONY: all refs check count clean

all: rubber-stamp.pdf rubber-stamp-supplement.pdf submission.txt

refs:
	python3 latex/refs.py

check: refs
	@command -v prose-check >/dev/null || { echo "prose-check is not installed: uv tool install git+https://github.com/Vein05/prose-check"; exit 1; }
	$(PROSE) writeup.md latex/supplement/*.tex

count: refs
	python3 latex/wordcount.py writeup.md

rubber-stamp.pdf: writeup.md latex/report.lua latex/report-template.tex latex/rubberstamp.sty latex/postprocess.py figures/pdf/*.pdf figures/icons/*.pdf check count
	mkdir -p latex/build
	pandoc writeup.md -f markdown-auto_identifiers --lua-filter latex/report.lua --template latex/report-template.tex \
	  --wrap=none -o latex/build/report-raw.tex
	python3 latex/postprocess.py latex/build/report-raw.tex latex/build/rubber-stamp.tex
	TEXINPUTS=latex:: pdflatex -interaction=nonstopmode -output-directory=latex/build latex/build/rubber-stamp.tex > /dev/null; \
	  TEXINPUTS=latex:: pdflatex -interaction=nonstopmode -output-directory=latex/build latex/build/rubber-stamp.tex | grep -E "^!|Output written|Overfull"; true
	cp latex/build/rubber-stamp.pdf $@

submission.txt: writeup.md latex/submission.py latex/wordcount.py refs
	python3 latex/submission.py

figures/icons/%.pdf:
	python3 latex/make_icons.py

rubber-stamp-supplement.pdf: latex/supplement/*.tex latex/rubberstamp.sty latex/style_supplement.py figures/icons/*.pdf check
	mkdir -p latex/build
	python3 latex/style_supplement.py latex/supplement/supplement.tex latex/build/supplement.tex
	TEXINPUTS=latex:: pdflatex -interaction=nonstopmode -output-directory=latex/build latex/build/supplement.tex > /dev/null; \
	  TEXINPUTS=latex:: pdflatex -interaction=nonstopmode -output-directory=latex/build latex/build/supplement.tex | grep -E "^!|Output written|Overfull"; true
	cp latex/build/supplement.pdf $@

clean:
	rm -f latex/supplement/*.aux latex/supplement/*.log latex/supplement/*.out latex/supplement/supplement.pdf
	rm -rf latex/build
