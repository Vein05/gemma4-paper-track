#!/usr/bin/env python3
"""Word count of writeup.md as a reader sees it: all text including tables and captions; Markdown syntax, URLs in
angle brackets and HTML comments removed. The competition allows 3,000 words.

The reference list does not count toward the limit (host Elan Markowitz, Kaggle forum, 2026-10-27, threads 749546
and 743255: "References will not count"; title, abstract, captions and tables do; figures and supplementary material
do not). It is still printed, but the limit check uses the count without it."""
import re, sys
t = open(sys.argv[1]).read()
t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)          # images
t = re.sub(r"<https?://[^>]+>", "URL", t)              # autolinks count as one word
t = re.sub(r"^\|?[\s|:-]+\|?$", "", t, flags=re.M)   # table separator rows
t = re.sub(r"[#*|`]", " ", t)
n = len(re.findall(r"\S+", t))
refs = t.split("References", 1)[1] if "References" in t else ""
r = len(re.findall(r"\S+", refs))
print(f"{n - r} words counted, without the reference list, which does not count ({n} with its {r}); limit 3,000")
sys.exit(1 if n - r > 3000 else 0)
