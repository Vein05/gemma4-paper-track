# Rubber Stamp: Gemma 4 Scores Its Own Failing Patches as Sure to Pass

Code, data and outputs for a submission to the paper track of the Gemma 4 Developer Agent competition on Kaggle.
Draft writeup: `paper/writeup.md`.

## Finding

Nine open models scored the chance that a SWE-bench Verified patch passes its hidden tests. The judge saw the issue
and one patch, never the author. Gemma 4 31B gives a score of 100 to 57–61% of its own failing patches in three patch
sets, against 20–35% of other writers' failing patches; outside judges scoring the same patches do not follow it.

| Patch set | Gemma's patches | Own failing patches scored 100 | Self-judging gap [95%] |
|---|---|---|---|
| 50 Mini issues | public runs in four other harnesses | 61% | +0.135 [0.060, 0.210] |
| the same 50 issues | ours, mini-SWE-agent (the other writers' harness) | 57% | +0.070 [−0.024, 0.168] |
| 193 held-out issues | ours, mini-SWE-agent | 61% | +0.074 [0.022, 0.126] |

The ranking gap halves once Gemma's patches come from the same harness as the other writers', and on the held-out
issues it holds only with an 8,000-token re-ask added after the plan was fixed. Five other models show no gap. As a
check of Gemma's patches, GLM-4.5 and Kimi-K2 beat Gemma by 0.16 and 0.14 AUROC.

## Layout

| Path | Contents |
|---|---|
| `paper/` | draft writeup, bibliography, figures |
| `spec/` | analysis plans, each committed before its data was computed (see the git history) |
| `scripts/` | agent runner, grading, judging and analysis code |
| `scripts/mcsr/` | Slurm jobs for the agent runs and grading |
| `scripts/derived/` | per-call judge outputs (`selfpref_*.jsonl` on the Mini issues, `fresh_*.jsonl` on the new patches) and the summaries behind every number |
| `data/mcsr-runs/` | Gemma 4 31B's mini-SWE-agent runs: patches (`preds.jsonl`), labels, run configuration, trajectories; `gold*` hold the reference-patch check |
| `data/public/` | other writers' patches with their SWE-bench labels, and the public Gemma 4 patches (sources in `data/README.md`) |
| `citations.md` | cited works, copied from primary sources |

In `data/mcsr-runs/`, cluster paths are replaced by `<workdir>` and `<user>`. `mini50/labels.jsonl` holds an outdated
label for `django__django-11848` (its first run failed to start); the analyses leave that issue out.

## Reproduce

Analyses need no API calls and read only files in this repository:

```bash
pip install numpy scipy
cd scripts
python3 self_judging_replication.py      # five-model comparison, mixed-harness patches (Section 3.3)
python3 own_patch_mechanism.py           # Section 3.4
python3 self_check_fix.py                # Gemma-only signals (Section 3.5)
python3 fresh_judging.py analyze --runs main-a,main-b \
  --judges gemma4-31b,gpt-oss-20b,qwen35-9b,glm47-flash,qwen3-coder,gpt-oss-120b,glm-4.5,kimi-k2,llama-4-maverick
                                         # held-out issues (Sections 3.1, 3.2); add --leave-out-reasked all
python3 mini50_analysis.py --drop django__django-11848   # matched-harness patches on the Mini issues
python3 outside_judge_check.py           # Section 3.5, Figure 2
```

Judging again calls models through OpenRouter (`scripts/self_preference.py`, `scripts/fresh_judging.py run`, needs
`OPENROUTER_API_KEY`); the study's API cost was $12.36. The agent runs need one 46 GB GPU, vLLM and Apptainer
(`scripts/run_gemma_mini.py`, `scripts/mcsr/run_pilot.sbatch`); grading uses `scripts/eval_apptainer.py`.

## Data

All inputs are public: SWE-bench Verified and SWE-bench Verified Mini, Gemma 4 31B agent runs published on Hugging
Face by a third party, and mini-SWE-agent submissions from SWE-bench experiments. Revisions and licences are listed in
`data/README.md`. No competition data is used.
