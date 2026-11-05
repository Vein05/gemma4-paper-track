# Gemma 4 Gives Its Failing Patches Full Marks

Gemma 4 gives most of its own failing patches the top score when it judges them without being told who wrote them.
The trust goes with the edit, and failing repository tests let Gemma repair some of these patches.

**[Read the paper (PDF)](paper/rubber-stamp.pdf)** and the [supplement (PDF)](paper/rubber-stamp-supplement.pdf).
Kaggle paper track, Gemma 4 Developer Agent.

![Gemma 4 31B approves most of its failing patches, and the extra trust goes with the edit](paper/figures/fig-trust.png)

## What we found

Coding agents often decide whether a patch is finished by asking the model that wrote it. We asked Gemma 4 31B and
other models to score SWE-bench Verified patches without naming their writer, and compared each judge with judges
from other model families on the same patch.

- **Gemma 4 31B rubber-stamps its failing patches.** On held-out SWE-bench Verified issues, it gives the top score to
  52 of its 85 failing patches, while outside judges score the same patches lower. It does the same on another team's
  Gemma run on SWE-bench Lite and on contest programs it wrote without an agent.
- **The trust goes with the edit.** Other writers' failing patches that make Gemma's edit get extra trust from Gemma,
  20 points on SWE-bench Lite, while smaller Gemma 4 models give the 31B's failing patches no measurable extra trust.
- **Checks that Gemma runs itself leave the trust in place.** Thinking before scoring, testing the patch in a shell
  and LoRA fine-tuning on labeled patches each leave most rubber-stamped patches approved.
- **Tests that Gemma did not write let it repair some patches.** Shown the repository tests its patch breaks, Gemma
  repairs 9 of the 52 rubber-stamped failing patches, against 3 after a plain second look. The same step breaks 4
  correct patches.

## What is here

| Path | What it is |
|---|---|
| [`paper/rubber-stamp.pdf`](paper/rubber-stamp.pdf) | The paper. |
| [`paper/rubber-stamp-supplement.pdf`](paper/rubber-stamp-supplement.pdf) | The detail behind each section of the paper: setup, the judge prompt, grading checks, each test with its plan and reading, and cost. |
| [`paper/writeup.md`](paper/writeup.md) | The paper as Markdown (the PDF's source; `cd paper && make` rebuilds both PDFs and `submission.txt`). |
| [`paper/submission.txt`](paper/submission.txt) | Every field of the Kaggle Writeup form, built from `writeup.md`. |
| [`spec/`](spec/) | Every analysis plan, each written before its data was computed. |
| [`scripts/`](scripts/) | Agent runner, grading, judging, the shell judge, LoRA training, the existing-test check, the repair run and every analysis; `scripts/lab/` and `scripts/mcsr/` run the GPU jobs; `scripts/derived/` holds every judge answer and the summary behind each number. |
| [`data/`](data/) | Gemma 4 31B's held-out agent runs (patches, labels, trajectories), its LiveCodeBench programs, the hand codes and the public patches we judged; sources and what is left out in `data/README.md`. |
| [Hugging Face: `vein05/gemma4-paper-track-data`](https://huggingface.co/datasets/vein05/gemma4-paper-track-data) | The raw runs too large for this repository: the shell-judge runs, the existing-test check and repair runs, the LoRA scores, the LiveCodeBench model sweep, the smaller-Gemma runs, the probe features and every judge prompt. |

## Compute

The project used about 74 GPU-hours, 59 on one A100 80 GB and 15 on L40S. At RunPod on-demand prices this compute
costs about $122. API judging through OpenRouter is listed in the supplement (Section G).

## AI disclosure

Claude Opus 5.5 was used in this project.
