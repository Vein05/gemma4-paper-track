#!/usr/bin/env python3
"""Build-time marks for the supplement, so the source stays plain LaTeX: tinted header rows in every table, Gemma 4
31B's rows tinted in its color, "Gemma" / "outside judges" colored in prose (as postprocess.py does for the paper),
and signed numbers written in math mode ($+0.135$, $-7.1$) set as text so their digits match the text font.

Usage: python3 latex/style_supplement.py latex/supplement/supplement.tex latex/build/supplement.tex
"""
import re, sys

GEMMA = re.compile(r"(?<![\w{-])(Gemma(?:~4 31B|~4| 4 31B| 4)?)(?![\w-]|~3| 3)")
OUTSIDE = re.compile(r"(?<![\w{])(outside judges?)(?![\w}])")
NUMBER = re.compile(r"\$([+-]?)(\d[\d.,]*)\$")


def number(m):
    return {"+": "+", "-": "\\textminus{}", "": ""}[m.group(1)] + m.group(2)


def color(text):
    return OUTSIDE.sub(r"\\outside{\1}", GEMMA.sub(r"\\gemma{\1}", text))


src, dst = sys.argv[1], sys.argv[2]
out, started, in_tab, in_head, in_box = [], False, False, False, False
for line in open(src).read().split("\n"):
    s = line.lstrip()
    if s.startswith("\\begin{document}"):
        started = True
    if s.startswith("\\begin{tabular}"):
        in_tab = True
        line = line.replace("@{}", "")  # with @{}, colortbl's row tints overhang the rules by a column gap
    elif s.startswith("\\end{tabular}"):
        in_tab = False
    elif s.startswith("\\begin{promptbox}"):
        in_box = True
    elif s.startswith("\\end{promptbox}"):
        in_box = False
    if started and not s.startswith("%"):
        line = NUMBER.sub(number, line)
    if in_tab:
        if s.startswith("\\toprule"):
            in_head = True
        elif s.startswith("\\midrule") and in_head:
            in_head = False
        elif in_head and s:
            line = "\\rowcolor{headbg}" + line
        elif re.match(r"Gemma(~| )4 31B &", s):
            line = "\\rowcolor{gemmasoft}" + line
    elif started and not in_box and not s.startswith(("\\section", "\\rstitle", "\\label", "%")):
        if s.startswith("\\paragraph{"):
            i = line.index("}") + 1
            line = line[:i] + color(line[i:])
        else:
            line = color(line)
    out.append(line)
open(dst, "w").write("\n".join(out))
