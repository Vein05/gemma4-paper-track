<h1 align="center">Neither Gemma 4 nor the Existing Tests Catch Wrong Fixes</h1>

<p align="center">
  Gemma 4 gives full marks to failing patches from equally strong agents as often as to its own.
  Seven in ten failing patches from 32 public models pass every existing test, and on one issue in ten the correct fix
  breaks one.
</p>

<p align="center">
  <a href="paper/rubber-stamp.pdf"><img alt="Paper (PDF)" src="https://img.shields.io/badge/paper-PDF-B31B1B?logo=data:image/svg%2Bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxZW0iIGhlaWdodD0iMWVtIiB2aWV3Qm94PSIwIDAgMjQgMjQiPjxwYXRoIGZpbGw9IndoaXRlIiBkPSJNMTkgM0g1Yy0xLjEgMC0yIC45LTIgMnYxNGMwIDEuMS45IDIgMiAyaDE0YzEuMSAwIDItLjkgMi0yVjVjMC0xLjEtLjktMi0yLTJtLTkuNSA4LjVjMCAuOC0uNyAxLjUtMS41IDEuNUg3djJINS41VjlIOGMuOCAwIDEuNS43IDEuNSAxLjV6bTUgMmMwIC44LS43IDEuNS0xLjUgMS41aC0yLjVWOUgxM2MuOCAwIDEuNS43IDEuNSAxLjV6bTQtM0gxN3YxaDEuNVYxM0gxN3YyaC0xLjVWOWgzem0tNi41IDBoMXYzaC0xem0tNSAwaDF2MUg3eiIvPjwvc3ZnPg=="></a>
  <a href="paper/rubber-stamp-supplement.pdf"><img alt="Supplement (PDF)" src="https://img.shields.io/badge/supplement-PDF-B31B1B?logo=data:image/svg%2Bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxZW0iIGhlaWdodD0iMWVtIiB2aWV3Qm94PSIwIDAgMjQgMjQiPjxwYXRoIGZpbGw9IndoaXRlIiBkPSJNMTkgM0g1Yy0xLjEgMC0yIC45LTIgMnYxNGMwIDEuMS45IDIgMiAyaDE0YzEuMSAwIDItLjkgMi0yVjVjMC0xLjEtLjktMi0yLTJtLTkuNSA4LjVjMCAuOC0uNyAxLjUtMS41IDEuNUg3djJINS41VjlIOGMuOCAwIDEuNS43IDEuNSAxLjV6bTUgMmMwIC44LS43IDEuNS0xLjUgMS41aC0yLjVWOUgxM2MuOCAwIDEuNS43IDEuNSAxLjV6bTQtM0gxN3YxaDEuNVYxM0gxN3YyaC0xLjVWOWgzem0tNi41IDBoMXYzaC0xem0tNSAwaDF2MUg3eiIvPjwvc3ZnPg=="></a>
  <a href="https://huggingface.co/datasets/vein05/gemma4-paper-track-data"><img alt="Dataset on Hugging Face" src="https://img.shields.io/badge/dataset-Hugging%20Face-FF9D00?logo=huggingface&logoColor=white"></a>
  <a href="https://www.kaggle.com/competitions/gemma-4-developer-agent-paper"><img alt="Kaggle paper track, Gemma 4 Developer Agent" src="https://img.shields.io/badge/Kaggle-Gemma%204%20Developer%20Agent-20BEFF?logo=kaggle&logoColor=white"></a>
</p>

<p align="center">
  <br>
  <img src="paper/figures/fig-writers.png" alt="Gemma 4 31B trusts failing patches more when their writer is stronger, and its extra trust in its own failing patches halves against equally strong writers" width="88%">
  <br><br>
</p>

## What we found

Coding agents often decide whether a patch is finished by asking a model, often the one that wrote it. We asked Gemma 4
31B and eight other models to score SWE-bench patches without naming their writer, and graded every patch with the
hidden tests. Gemma's extra trust in a patch is its score minus the mean score of judges from other model families.

- **Gemma 4 gives equally strong writers' failing patches the top score as often as its own.** By the usual measure, against five public
  agents of mixed strength, Gemma's extra trust in its own failing patches is 16.3 points. Against the seven public
  agents that solve about as many held-out SWE-bench Verified issues as Gemma, chosen by a rule fixed before scoring,
  it is 8.7 points. On Go, Ruby and PHP issues it scores 100 on 76% of its own failing patches and on 68% of four
  stronger agents' failing patches.
- **Most failing patches pass every existing test, and more of them as agents get stronger.** Across 32 public models
  in the same agent, 71% of the failing patches that change code pass every existing test that SWE-bench runs. Most of
  Gemma's own failing patches are such wrong fixes, and Gemma gives about three quarters of them the top score.
  Thinking before scoring, testing the patch in a shell and LoRA fine-tuning each left most of them approved.
- **On one issue in ten, the correct fix breaks an existing test.** On 45 of 426 issues, the reference fix breaks a
  test that its own pull request edits or deletes (`data/outdated-test-issues/`). Shown the existing tests its patch
  breaks, Gemma repairs 14 of 26 held-back failing patches on the held-out issues, against 7 after a second look. But
  on SWE-bench Lite, an outdated test held back 13 correct patches, and Gemma broke 12 of them when shown the test,
  against 2 after a second look. Having Gemma label these tests first spares most of the correct patches,
  but the net gain in passing patches is within noise.

## Reproduce

```
./reproduce.sh main
```

This recomputes the main paper's claims from the released data and prints each one next to the paper's value. It takes
about three minutes, needs no GPU and calls no model. It downloads only the files those analyses read: 92 MB of the
2.1 GB Hugging Face dataset, plus Gemma's SWE-bench Lite patches from the team that published them. The run fails if
any downloaded file goes unread. Everything goes into `.reproduce/`, and the repository's own files stay as they are.
It needs `uv`, or Python 3.11 or newer.

`./reproduce.sh supplement` and `./reproduce.sh all` are not written yet.

## What is here

| Path | What it is |
|---|---|
| [`paper/rubber-stamp.pdf`](paper/rubber-stamp.pdf) | The paper. |
| [`paper/rubber-stamp-supplement.pdf`](paper/rubber-stamp-supplement.pdf) | Setup, judge prompt, grading checks, every test and its cost. |
| [`paper/writeup.md`](paper/writeup.md) | The paper as Markdown, the PDF's source (`cd paper && make` rebuilds it). |
| [`scripts/`](scripts/) | Agent runs, grading, judging, repair and every analysis; `scripts/derived/` holds each judge answer and number. |
| [`data/`](data/) | Gemma 4 31B's agent runs, its contest programs and the public patches we judged (see `data/README.md`). |
| [Hugging Face: `vein05/gemma4-paper-track-data`](https://huggingface.co/datasets/vein05/gemma4-paper-track-data) | The raw runs too large for this repository, and every judge prompt. |

## Compute

The project used about 113 GPU-hours, 97 on one A100 80 GB and 15 on L40S. At RunPod on-demand prices this compute
costs about $191. API judging through OpenRouter is listed in the supplement (Section G).

## License

The code is under the [Apache License 2.0](LICENSE). Third-party data in `data/public/` keeps its source's terms
([`data/README.md`](data/README.md)).

## AI disclosure

Claude Opus 5.5 and Claude Fable 5.2 were used in this project.
