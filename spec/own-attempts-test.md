# Spec: own-attempts test (CHARTER claim 3, self-verification)

Written 2026-10-05, before any model call on this data. Terms follow `../GLOSSARY.md`.

## Question

When Gemma 4 judges patches that Gemma 4 itself wrote, does pointwise rating choose among its attempts as well as
pairwise comparison, and is the same-conditions result (claim 1) the same as on other agents' patches? The other
three models judge the same patches as a check on whether any difference is about judging one's own work.

## Data

- Gemma 4 31B-it agent attempts on SWE-bench Verified Mini (50 tasks: 25 django, 25 sphinx) from six public
  third-party Hugging Face datasets (`n-pelleriti/alphadiana-*`; shas, runs, harnesses and extraction rules in
  `data/public/gemma4-own-attempts/README.md`). Four agent harnesses (SWE-agent, OpenCode, OpenClaw, ZeroClaw) plus
  one call without an agent loop; one attempt per task per run; served with vLLM in bf16. Labels are the official
  SWE-bench evaluator reports. Issue text from `MariusHobbhahn/swe-bench-verified-mini` (sha
  `b316c349947c29963fce3f4a65967c9807a4b673`).
- Usable attempt: non-empty patch with an evaluator label. Test-file hunks removed, duplicate patches dropped,
  patches over 30,000 characters dropped (same rule as `spec/post-cutoff-test.md`; drops one patch of 1.1M characters).
- Pool per issue: all unique usable patches, for issues with at least one passing and one failing patch. 18 issues,
  pools of 2–6 patches, about half of the patches pass. Random choice is right at the pool's pass share.
- Limitations stated now: 18 issues give wide intervals; SWE-bench Verified issues predate Gemma 4's training
  cutoff, so remembered fixes are possible; the attempts come from different harnesses, not repeated samples of one.

## Methods and measures

Same selection methods, prompts, decoding and tie rules as `spec/selection-test.md` (rating answer only, rating
reasoning first, averaged rating of 3 samples at temperature 0.7, comparison answer only and reasoning first on
every ordered pair, rating then comparison among tied). Calls per pool: 5 per patch for ratings, 2 per ordered pair
for comparisons; about 811 calls per model.

Reported per model: selection accuracy and calls per pool for every method, with the paired difference to
reasoning-first comparison (95% interval, 2,000 bootstrap resamples of issues). From the same calls: pair accuracy
in the four conditions on every pass/fail pair inside the pools, tie rates, and the reasoning-first difference
comparison minus rating with its interval.

Reading rule, fixed now: same as the selection test (a rating method within 0.05 of reasoning-first comparison,
interval of the difference excluding −0.10, fewer calls). Self-verification is compared descriptively: Gemma's
accuracy on its own patches vs the other models' accuracy on the same patches. With 18 issues this is reported as
a small-sample check, not a claim.

## Outputs

Rows `scripts/derived/selection-own_<tag>.jsonl`; summary `scripts/derived/own_attempts_summary_<date>.json`;
W&B group `own-attempts-test`; run log in `changelog/<date>.md` under "Run log: own-attempts test".

## Cost estimate

About 811 calls per model; Gemma about $1, the other three under $1 together.

## Addendum, 2026-10-05: self-preference check and same-issue control (written before the control's model calls)

**Why added.** After the own-attempts runs, Gemma's reasoning-first ratings tied on 52.5% of pass/fail pairs of its
own patches (20.7% on SWE-agent patches). Gemma's score minus the mean of the other three judges was +19.3 points on
its own failing patches and −9.8 on SWE-agent failing patches (difference +29.1, interval [15.0, 45.3];
`scripts/self_preference.py`). This analysis was not planned. The comparison is confounded: the two patch sets come
from different issues, repositories and benchmarks.

**Control (fixed now, before its calls).** Same 50 SWE-bench Verified Mini issues, patches by other agents:
six mini-SWE-agent submissions from the public `SWE-bench/experiments` repository (one scaffold, different models;
patches and per-issue reports from the public `swe-bench-submissions` bucket):
`20250807_mini-v1.7.0_gpt-oss-120b`, `20250822_mini-v1.9.1_glm-4.5`, `20250802_mini-v1.0.0_qwen3-coder-480b-a35b-instruct`,
`20250720_mini-v0.0.0-Llama-4-Maverick-17B-Instruct`, `20250807_mini-v1.7.0_kimi-k2-instruct`,
`20251209_mini-v1.17.2_devstral-small-2512`. Same patch processing (test hunks removed, 30,000-character limit,
duplicates dropped). Every usable Gemma 4 patch on the 50 issues and every control patch gets one reasoning-first
rating (temperature 0, same prompt) from each of the four judges; ratings already collected are reused.

**Measures.** Primary: for failing patches, (Gemma's score minus the mean of the other three judges) on Gemma's own
patches minus the same quantity on the six control writers' patches, same 50 issues; 95% interval from 2,000
bootstrap resamples of issues. Same for passing patches. Secondary (family check, same construction): gpt-oss-20b on
gpt-oss-120b patches, GLM-4.7-flash on GLM-4.5 patches, Qwen3.5-9B on Qwen3-Coder patches, each against the
remaining control writers. Reading rule: self-preference is supported for Gemma if the primary interval for failing
patches excludes 0. Reported whichever way it falls; the family checks are descriptive (a family is not the same
model).
