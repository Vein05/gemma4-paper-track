# Spec: does Gemma 4 rubber-stamp its own patches on fresh issues from the same harness as the controls?

FROZEN 2026-10-05 (user's decisions: N = 200, k = 1, mini-SWE-agent v1.7.0), committed to the release repo before any
Gemma agent run outside the pilot. The main run starts only if the pilot meets the stop rule below. Terms follow
`GLOSSARY.md`.

## Why

On the 50 SWE-bench Verified Mini issues, Gemma 4 31B's self-judging gap is +0.135 [0.060, 0.210] and its
rubber-stamp rate is 61% (49 of 80 own failing patches scored 100). Five other models show no gap (pooled −0.036
[−0.089, 0.016]). Two weaknesses: the Gemma result was found in an exploratory look and its ratings are reused, and
every Gemma patch came from a different harness (SWE-agent, openclaw, opencode, zeroclaw) than every control patch
(mini-SWE-agent). This test removes both: new issues, and Gemma patches written by mini-SWE-agent.

A selection effect could also produce the gap: an agent submits a patch once its own loop accepts it, so its failing
patches are those that fooled the model once already. If harnesses differ in how much they check before submitting,
the gap could come from the harness, not the model. This test separates the two.

## Issues

- Pool: SWE-bench Verified issues (`princeton-nlp/SWE-bench_Verified`, test split, revision recorded at download),
  minus the 50 Mini issues, minus issues where none of the five control entries has a usable patch (as in the
  original study, which used whatever control patches existed). Requiring all five left 203 of 450 issues and
  would favor easier issues; the looser rule leaves 447 (`scripts/fresh_issues.py`, 2026-10-05).
- Usable patch: non-empty after removing test-file hunks, at most 30,000 characters, with a SWE-bench report (as in
  `scripts/self_preference.py`).
- Pilot: 5 issues drawn first (seed 1), excluded from the sample: astropy__astropy-14995, django__django-16569,
  django__django-7530, scikit-learn__scikit-learn-13496, sympy__sympy-20438.
- Sample: the remaining pool in a fixed random order (seed 0, `sample.json`); the sample is its first N issues.
- **N = 200, k = 1** (decided 2026-10-05): the first 200 issues of the fixed order. Bootstrap of the existing data
  gives a 95% half-width of the gap of 0.051 for N = 200, k = 1 (`todo.md`). Run as two jobs, positions 0–99 and
  100–199 (`--issues order:0-100`, `order:100-200`).

## Gemma patches (new)

- Agent: mini-SWE-agent v1.7.0 (used by two control entries; controls span v0.0.0 to v1.17.2), its default
  SWE-bench config, unchanged.
- Runner: `scripts/run_gemma_mini.py`, mini-SWE-agent 1.7.0's own agent and `extra/swebench.yaml` config (250 steps,
  temperature 0, 60 s command timeout) unchanged; its Docker environment is replaced by a writable Apptainer
  sandbox of the same image.
- Model: `gemma-4-31B-it-qat-w4a16-ct` (the competition checkpoint) served by vLLM; sampling settings
  of that config. For k = 2 the two attempts differ only in the sampling seed.
- Compute (changed 2026-10-05, before any agent run): one NVIDIA L40S (46 GB) per Slurm job on MCSR Magnolia
  (`scripts/mcsr/run_pilot.sbatch`), vLLM `--max-model-len 131072` (65536 if the KV cache does not fit), instead of
  the shared lab A100. vLLM version recorded in each job log.
- Sandbox: SWE-bench instance images run with Apptainer. Lab server: `--fakeroot --ignore-subuid`. Magnolia: no
  fakeroot (its fakeroot library needs glibc 2.38, newer than the images'); the sandbox is built unprivileged, so its
  files belong to the job's user and the agent can write to `/testbed`, use conda, git and pip (checked 2026-10-05 on
  `django__django-16569`).
- Labels: SWE-bench evaluation of each final patch in the same sandbox type (`scripts/eval_apptainer.py`, swebench
  4.1.0 grading code, current `swebench/sweb.eval.*` images). Validation before use, on 30 issues stratified by repo:
  (a) the official reference patches must all resolve; (b) control patches that `git apply` applies cleanly must
  match their official labels.
- Validation so far (2026-10-05): 27 of 30 control patches matched. All 3 mismatches were official passes that
  `git apply` rejected on today's images, which were rebuilt in 2026-08 and differ from the 2025 images in
  `setup.py`, `tox.ini` or `build/` files that those patches also touched. Control labels therefore stay the
  official 2025 ones; Gemma patches are written and graded on the current images. Recorded as a limit.
  (a) passed: the official reference patches of the same 30 issues all resolved, each applied by plain `git apply`.
- Magnolia grades without fakeroot, so check (b) is repeated there before its labels are used
  (`eval_apptainer.py validate`, same entry and n). Until it agrees, pilot labels come from the lab server.

## Control patches (existing)

The five entries in `bash-only/` of the public `swe-bench-submissions` bucket: `20250802_mini-v1.0.0_qwen3-coder-480b-
a35b-instruct`, `20250807_mini-v1.7.0_gpt-oss-120b`, `20250822_mini-v1.9.1_glm-4.5`,
`20250807_mini-v1.7.0_kimi-k2-instruct`, `20250720_mini-v0.0.0-Llama-4-Maverick-17B-Instruct`. Labels from their
reports.

## Judges

The same nine judges, prompt (`Q_P1`), settings and parser as `spec/self-judging-replication.md`, through
`scripts/self_preference.py`. Gemma 4 31B as judge is the hosted model on OpenRouter, as in the original study.
Unparsed answers are asked once more, then left out. Analyses use patches with a parsed score from all nine judges.

## Measures (fixed at freeze)

- **Primary:** Gemma's self-judging gap on the new patches, defined exactly as in `scripts/self_judging_replication.py`,
  95% interval from 2,000 bootstrap resamples of issues.
- Reading rule:
  - lower bound > 0 and point estimate ≥ 0.068 (half the original): replicated;
  - lower bound > 0 and point estimate < 0.068: replicated, smaller;
  - interval includes 0: not replicated. Then judge other models' patches from non-mini harnesses in public
    `SWE-bench/experiments` entries to test the harness explanation (separate spec).
- Secondary, reported for every judge with own patches: rubber-stamp rate on own vs other writers' failing patches
  (share scored 100), leniency on failing patches matched by issue, the five-model pooled gap.
- Decision test (`todo.md` section 3) and token-probability ratings (`todo.md` section 4) get their own specs before
  their data is computed; they use these patches.

## Cost and stopping

- Agent runs: MCSR Magnolia (free academic allocation), no API cost. Stop if the pilot shows a resolve rate under 10% or a median run over 30 minutes,
  and report before the full run.
- Judging: about 9 judges × (N·k + 5N) patches; at the earlier $0.00076 per call, about $8 for N = 200, k = 1. Stop and
  report if spend passes 1.5× the estimate.
- W&B project `gemma4-paper-track`, group `fresh-replication`; changelog entry per run.
