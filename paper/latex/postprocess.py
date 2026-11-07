#!/usr/bin/env python3
"""Add the report's links and color marks to the LaTeX that pandoc writes from writeup.md.

- Author-year citations in the prose ("Roytburg et al. (2026)", "(Jimenez et al., 2023)", dataset authors) become
  violet links to their reference entry. Keys and years come from ../references.bib, so nothing is typed here.
- Reference list items get anchors (same order as refs.py writes them) and a hanging indent.
- "Gemma" (Gemma 4, not Gemma 3) and "outside judge(s)" get the figures' colors in prose; tables, headings, figure
  includes and the reference list are left alone.

Usage: python3 latex/postprocess.py <in.tex> <out.tex>   (run from paper/)
"""
import os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
BIB = os.path.join(HERE, "..", "references.bib")
MD = os.environ.get("REPORT_MD", os.path.join(HERE, "..", "writeup.md"))  # REPORT_MD: build a draft


def entries(bib):
    out = {}
    for m in re.finditer(r"@\w+\{([^,]+),(.*?)\n\}", bib, flags=re.S):
        out[m.group(1)] = dict((k.lower(), v.strip()) for k, v in
                               re.findall(r"^\s*(\w+)\s*=\s*\{(.*)\},?\s*$", m.group(2), flags=re.M))
    return out


def clean(s):
    return re.sub(r"\\(?:url|texttt)\{([^}]*)\}", r"\1", s).replace("{", "").replace("}", "")


src, dst = sys.argv[1], sys.argv[2]
tex = open(src).read()
E = entries(open(BIB).read())
keys = re.search(r"<!-- cite: (.*?) -->", open(MD).read()).group(1).split()
surname = lambda k: clean(E[k]["author"]).split(" and ")[0].split()[-1]

# 1. Citations in the prose. Person-authored works: "Surname et al." with an optional year.
cites = 0
for k in keys:
    a = clean(E[k]["author"])
    if " " not in a.split(" and ")[0]:
        continue  # organisation or handle as author: handled below
    s, y = surname(k), E[k].get("year", "")
    pat = re.compile(rf"(?<![\w\\{{]){re.escape(s)} et al\.(?: \({y}\)|, {y})?")
    tex, n = pat.subn(lambda m: f"\\citelink{{{k}}}{{{m.group(0)}}}", tex)
    cites += n
# Handles and organisations, cited by name in parentheses.
for k, text in [("swebenchverifiedmini", "(MariusHobbhahn)"), ("alphadiana", "(n-pelleriti)"),
                ("swebenchexperiments", "(SWE-bench experiments)"), ("miniswe", "(SWE-agent)")]:
    n = tex.count(text)
    tex = tex.replace(text, f"(\\citelink{{{k}}}{{{text[1:-1]}}})")
    cites += n

# 2. Reference list: anchors and hanging indent.
head, sep, refs = tex.partition("\\rsection{}{References}")
order = sorted(keys, key=lambda k: clean(E[k]["author"]).split(" and ")[0].split()[-1].lower())
items = re.split(r"\\item\s*", refs)
assert len(items) - 1 == len(order), (len(items) - 1, len(order))
body = "".join(f"\\item[]\\hypertarget{{ref:{k}}}{{}}{it.strip()}\n" for k, it in zip(order, items[1:]))
body = re.sub(r"\\end\{itemize\}.*", "", body, flags=re.S)
refs = ("\n{\\small\\begin{itemize}[leftmargin=1.4em,itemindent=-1.4em,itemsep=0.35em,label={}]\n" + body +
        "\\end{itemize}}\n\n\\end{document}\n")

# 3. Color marks in prose lines only, on the first mention of each term per paragraph (2026-10-23: every mention
# read busy).
TERMS = [("gemma", r"(?<![\w{-])(Gemma(?: 4 31B| 4)?)(?![\w-]| 3)", r"\\gemma{\1}"),
         ("outside", r"(?<![\w{])(outside judges?)(?![\w}])", r"\\outside{\1}")]
out, skip, started, seen = [], False, False, set()
for line in head.split("\n"):
    if not line.strip():
        seen.clear()
    if line.startswith("\\begin{document}"):
        started = True
    if line.startswith("\\begin{rtable}"):
        skip = True
    if started and not skip and "\\rsection" not in line and "\\rsubsection" not in line and "\\includegraphics" not in line:
        for key, pat, rep in TERMS:
            if key not in seen:
                line, n = re.subn(pat, rep, line, count=1)
                if n:
                    seen.add(key)
    if line.startswith("\\end{rtable}"):
        skip = False
    out.append(line)
tex = "\n".join(out) + sep + refs
open(dst, "w").write(tex)
print(f"{cites} citation links, {len(order)} reference anchors", file=sys.stderr)
