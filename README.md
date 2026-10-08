# Rubber Stamp: Gemma 4 Scores Its Own Failing Patches as Sure to Pass

Code, data and outputs for a submission to the paper track of the Gemma 4 Developer Agent competition on Kaggle.

## The paper

| File | What it is |
|---|---|
| **[`paper/rubber-stamp.pdf`](paper/rubber-stamp.pdf)** | **The main submission.** The paper (2,766 words including tables and references; the limit is 3,000). |
| [`paper/writeup.md`](paper/writeup.md) | The same paper as Markdown, the text of the Kaggle Writeup. It is the source of the PDF, so the two never differ. |
| [`paper/rubber-stamp-supplement.pdf`](paper/rubber-stamp-supplement.pdf) | Supplement, not part of the paper: setup details and the exact judge prompt, grading checks, re-asks and sensitivity analyses, the mechanism checks, the five-model table, per-judge tables, all submit-without-review rates, cost. |

`cd paper && make` rebuilds both PDFs (needs pandoc and pdflatex): it fills the reference list from
`references.bib`, checks the word count, and renders `writeup.md` through `latex/writeup.lua` and `latex/header.tex`.
The PDFs borrow the ICLR 2027 style file for their layout only; this is a preprint, not an ICLR submission.

## Finding

Nine open models scored the chance that a SWE-bench Verified patch passes its hidden tests. The judge saw the issue
and one patch, never the author. Gemma 4 31B gives a score of 100 to 57–61% of its own failing patches in three patch
sets, against 20–35% of other writers' failing patches; outside judges scoring the same patches do not follow it.

| Patch set | Gemma's patches | Own failing patches scored 100 | Self-judging gap [95%] |
|---|---|---|---|
| 50 Mini issues | public runs in four other harnesses | 61% | +0.135 [0.060, 0.210] |
| the same 50 issues | ours, mini-SWE-agent (the other writers' harness) | 57% | +0.066 [−0.025, 0.161] |
| 193 held-out issues | ours, mini-SWE-agent | 61% | +0.074 [0.022, 0.126] |

The ranking gap halves once Gemma's patches come from the same harness as the other writers', and on the held-out
issues it holds only with an 8,000-token re-ask added after the plan was fixed. Five other models show no gap. If an
agent submits without review the quarter of its held-out patches that its check trusts most, 61% pass with Gemma as
the check, 76% with Gemma's and Qwen3.5-9B's ranks averaged, and 84% with GLM-4.5.

## Layout

| Path | Contents |
|---|---|
| `paper/` | the paper (`rubber-stamp.pdf`), its Markdown source (`writeup.md`), the supplement, bibliography, figures (`figures/*.png` for the Writeup, `figures/pdf/` for the PDFs), build files (`latex/`, `Makefile`) |
| `spec/` | analysis plans, each committed before its data was computed (see the git history) |
| `scripts/` | agent runner, grading, judging and analysis code |
| `scripts/mcsr/` | Slurm jobs for the agent runs and grading |
| `scripts/derived/` | per-call judge outputs (`selfpref_*.jsonl` on the Mini issues, `fresh_*.jsonl` on the new patches) and the summaries behind every number |
| `data/mcsr-runs/` | Gemma 4 31B's mini-SWE-agent runs: patches (`preds.jsonl`), labels, run configuration, trajectories; `gold*` hold the reference-patch check |
| `data/public/` | other writers' patches with their SWE-bench labels, and the public Gemma 4 patches (sources in `data/README.md`) |
| `citations.md` | cited works, copied from primary sources |

In `data/mcsr-runs/`, cluster paths are replaced by `<workdir>` and `<user>`. `django__django-11848` on the Mini
issues was run twice (the first run failed to start); `mini50/` holds the second run's patch and label.

## Reproduce

Analyses need no API calls and read only files in this repository:

```bash
pip install numpy scipy
cd scripts
python3 self_judging_replication.py      # five-model comparison (Section 3.3; Supplement E)
python3 own_patch_mechanism.py           # mechanism checks (Supplement D)
python3 self_check_fix.py                # Gemma-only signals (Supplement I)
python3 fresh_judging.py analyze --runs main-a,main-b \
  --judges gemma4-31b,gpt-oss-20b,qwen35-9b,glm47-flash,qwen3-coder,gpt-oss-120b,glm-4.5,kimi-k2,llama-4-maverick
                                         # held-out issues (Sections 3.1, 3.2); add --leave-out-reasked all
python3 mini50_analysis.py              # matched-harness patches on the Mini issues
python3 outside_judge_check.py           # Section 3.4, Figure 2
python3 accept_decision.py               # Section 3.4, the submit-without-review table
```

Judging again calls models through OpenRouter (`scripts/self_preference.py`, `scripts/fresh_judging.py run`, needs
`OPENROUTER_API_KEY`). API cost as reported by OpenRouter per call (sums of the `cost` field in `scripts/derived/`):

| Run | Calls | Cost (USD) |
|---|---|---|
| Four judges on Gemma's own attempts (ratings reused) | 3,244 | 0.53 |
| Nine judges on the Mini issues, mixed-harness patches, reasoning off | 3,292 | 2.66 |
| Gemma 4 31B with thinking on, Mini issues | 401 | 0.51 |
| Nine judges on the held-out and matched-harness patches | 9,857 | 8.66 |
| Total | 16,794 | 12.36 |

gpt-oss-120b calls were reported at zero cost by their provider. The agent runs need one 46 GB GPU, vLLM and Apptainer
(`scripts/run_gemma_mini.py`, `scripts/mcsr/run_pilot.sbatch`); grading uses `scripts/eval_apptainer.py`.

## Data

All inputs are public: SWE-bench Verified and SWE-bench Verified Mini, Gemma 4 31B agent runs published on Hugging
Face by a third party, and mini-SWE-agent submissions from SWE-bench experiments. Revisions and licences are listed in
`data/README.md`. No competition data is used.
