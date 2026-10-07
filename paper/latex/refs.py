#!/usr/bin/env python3
"""Fill the reference list of writeup.md from ../references.bib (verified entries; see ../../citations.md).

Reads the keys in the `<!-- cite: ... -->` line and writes one Markdown entry per key, sorted by first author,
between `<!-- refs:start -->` and `<!-- refs:end -->`. Every field is copied from the bib entry (full author lists, no
"et al."); nothing is typed by hand.
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MD = os.path.join(HERE, "..", "writeup.md")
BIB = os.path.join(HERE, "..", "references.bib")


def entries(bib):
    out = {}
    for m in re.finditer(r"@\w+\{([^,]+),(.*?)\n\}", bib, flags=re.S):
        fields = dict((k.lower(), v.strip()) for k, v in re.findall(r"^\s*(\w+)\s*=\s*\{(.*)\},?\s*$", m.group(2), flags=re.M))
        out[m.group(1)] = fields
    return out


def clean(s):
    s = re.sub(r"\\(?:url|texttt)\{([^}]*)\}", r"\1", s)
    return s.replace("{", "").replace("}", "")


def authors(a):
    names = [clean(x).strip() for x in a.split(" and ")]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def fmt(f):
    parts = [authors(f["author"]) + "."]
    if "year" in f:
        parts.append(f["year"] + ".")
    t = clean(f["title"])
    parts.append("*" + t + "*" + ("" if t[-1] in "?!." else "."))
    url = f.get("url") or clean(f.get("howpublished", ""))
    if url:
        parts.append(f"<{url}>.")
    if "note" in f:
        parts.append(clean(f["note"]).rstrip(".") + ".")
    return " ".join(parts)


text = open(MD).read()
keys = re.search(r"<!-- cite: (.*?) -->", text).group(1).split()
E = entries(open(BIB).read())
missing = [k for k in keys if k not in E]
if missing:
    sys.exit(f"not in references.bib: {missing}")
surname = lambda k: clean(E[k]["author"]).split(" and ")[0].split()[-1].lower()
lines = [fmt(E[k]) for k in sorted(keys, key=surname)]
block = "<!-- refs:start -->\n" + "\n".join(f"- {l}" for l in lines) + "\n<!-- refs:end -->"
open(MD, "w").write(re.sub(r"<!-- refs:start -->.*?<!-- refs:end -->", lambda m: block, text, flags=re.S))
print(f"{len(lines)} references written", file=sys.stderr)
