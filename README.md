# Gemma 4 Rubber-Stamps Its Own Failing Patches

Gemma 4 gives most of its own failing patches the top score when asked to rank them (without being told who wrote
them). We find this happens far more often in Gemma 4 compared to other judges. A second judge lets an agent built on
Gemma pick out the patches it can submit without review.

**[Read the paper (PDF)](paper/rubber-stamp.pdf)** · [Supplement (PDF)](paper/rubber-stamp-supplement.pdf) ·
Kaggle paper track, Gemma 4 Developer Agent

![Gemma 4 31B's self-judging gap and its scores on failing patches](paper/figures/fig-results.png)

## What we found

Nine open models scored the chance that a SWE-bench Verified patch passes its hidden tests. Each judge saw the issue
and one patch, never the author.

- **Gemma rubber-stamps its own patches.** On 193 held-out issues, Gemma 4 31B gives a score of 100 to 61% of its own
  failing patches and to 35% of other models' failing patches. Judges from other model families do not share this
  extra trust.
- **Only Gemma shows it.** Five other models judging their own patches show no ranking gap and little leniency.
- **A second judge picks better.** If an agent submits without review the quarter of its patches that its check
  trusts most, 61% pass when Gemma checks itself and 84% when GLM-4.5 does.

## What is here

| Path | What it is |
|---|---|
| [`paper/rubber-stamp.pdf`](paper/rubber-stamp.pdf) | The paper. |
| [`paper/rubber-stamp-supplement.pdf`](paper/rubber-stamp-supplement.pdf) | Setup details, the judge prompt, grading checks, per-judge tables and cost. |
| [`paper/writeup.md`](paper/writeup.md) | The paper as Markdown (the PDF's source; `cd paper && make` rebuilds both PDFs and `submission.txt`). |
| [`paper/submission.txt`](paper/submission.txt) | Every field of the Kaggle Writeup form, built from `writeup.md`. |
| [`data/`](data/) | Gemma 4 31B's agent runs (patches, labels, trajectories) and the public patches we judged; sources in `data/README.md`. |
| [`scripts/`](scripts/) | Agent runner, grading, judging and analysis code; `scripts/derived/` holds every judge answer and the summaries behind each number. |
| [`spec/`](spec/) | Analysis plans, each committed before its data was computed. |
