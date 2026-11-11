#!/usr/bin/env python3
"""Write submission.txt: every field of the Kaggle Writeup form, filled from writeup.md.

Title is writeup.md's H1, the subtitle its `<!-- kaggle-subtitle: ... -->` line, the body the rest of writeup.md with
HTML comments removed, paragraphs unwrapped to one line each and figure links pointed at the public repository.
The other form fields are fixed below. `make` rebuilds the file, and make_release.sh copies it into release/.
"""
import os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MD = os.path.join(HERE, "..", "writeup.md")
OUT = os.path.join(HERE, "..", "submission.txt")
REPO = "https://github.com/Vein05/gemma4-paper-track"
RAW = "https://raw.githubusercontent.com/Vein05/gemma4-paper-track/main/paper/"

text = open(MD).read()
title = re.search(r"^# (.+)$", text, flags=re.M).group(1)
subtitle = re.search(r"<!-- kaggle-subtitle: (.*?) -->", text, flags=re.S).group(1)
subtitle = re.sub(r"\s+", " ", subtitle)

body = re.sub(r"<!--.*?-->\n?", "", text, flags=re.S)
body = re.sub(r"^# .+\n", "", body, count=1)
body = re.sub(r"\]\((figures/[^)]+\.png)\)", lambda m: "](" + RAW + m.group(1) + ")", body)
blocks = []
for block in re.split(r"\n\s*\n", body.strip()):
    lines = block.split("\n")
    if all(l.startswith("|") for l in lines):
        blocks.append(block)
    elif re.match(r"(- |\d+\. )", lines[0]):
        items = []
        for l in lines:
            if re.match(r"(- |\d+\. )", l):
                items.append(l)
            else:
                items[-1] += " " + l.strip()
        blocks.append("\n".join(items))
    else:
        blocks.append(" ".join(l.strip() for l in lines))
body = "\n\n".join(blocks)

count = subprocess.run([sys.executable, os.path.join(HERE, "wordcount.py"), MD], capture_output=True, text=True)
words = count.stdout.strip()

form = f"""Kaggle Writeup for "Google - The Gemma 4 Developer Agent Paper Track"
(https://www.kaggle.com/competitions/gemma-4-developer-agent-paper). Deadline: 2026-11-12, 23:59 UTC.
Built from paper/writeup.md by paper/latex/submission.py; edit writeup.md and run make, not this file.
Word count (paper/latex/wordcount.py): {words}. The subtitle adds {len(subtitle.split())} words.

Before submitting: make the GitHub repository public (the PDF links and the two figure images in the body point at
it), check that both figures show in the Writeup preview, and press Submit (a saved draft is not judged).

== Title ==
{title}

== Subtitle ==
{subtitle}

== Subtitle as entered (the Kaggle field holds 140 characters; this is its first sentence) ==
{subtitle.split(". ")[0]}.

== Track (if the form asks) ==
Overall Best Paper

== Card and thumbnail image (upload) ==
paper/figures/card-kaggle-upload.png
(square, with the 2:1 card paper/figures/card-kaggle.png in its middle band: Kaggle cuts a 2:1 cover and a square
thumbnail from one upload, and its default crops then give the card and the whole scene. Built by `make card` in
figures/gemma4-rubber-stamp/ of the research folder.)

== Project Links ==
Paper (PDF): {REPO}/blob/main/paper/rubber-stamp.pdf
Supplement (PDF): {REPO}/blob/main/paper/rubber-stamp-supplement.pdf
Code and data: {REPO}

== Project Files (upload) ==
paper/rubber-stamp.pdf
paper/rubber-stamp-supplement.pdf

== Body (paste into the Writeup editor) ==
"""
open(OUT, "w").write(form + body + "\n")
print(f"submission.txt written ({words})", file=sys.stderr)
