#!/usr/bin/env python3
"""Word count of writeup.md as a reader sees it: all text including tables, captions and references; Markdown
syntax, URLs in angle brackets and HTML comments removed. The competition allows 3,000 words."""
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
print(f"{n} words in total ({r} in the reference list, {n - r} without it); limit 3,000")
sys.exit(1 if n > 3000 else 0)
