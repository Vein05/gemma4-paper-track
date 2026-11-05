# Spec: before/after training-cutoff test (CHARTER claim 1, memorization check)

Written 2026-10-05, before any model call on this data. Terms follow `../GLOSSARY.md`.

## Question

Does the same-conditions result (pairwise comparison vs pointwise rating, ties separated) hold on issues created
after the judge's training cutoff, where the model cannot remember the upstream fix? Does pair accuracy change
between issues created before and after the cutoff?

## Data

- Source: public SWE-bench-Live submissions (`github.com/SWE-bench-Live/submission`, commit
  `cba8a6d3197cd53da09f8527cccbc689782302a6`, lite split, 13 agent and model combinations), with issue text and
  creation dates from `SWE-bench-Live/SWE-bench-Live` (lite split, revision `b51a86422e10cfd403beb4773e5a2947953e36ec`).
  300 Python issues created 2024-10-01 to 2025-03-30. Pass/fail labels are the submissions' own SWE-bench-Live
  evaluation results. Copied to `data/public/swe-bench-live/`; loader `scripts/live_data.py`.
- Patch writers are different from the main data (frontier and open agents of 2025–2026, not SWE-agent Llama
  models), so this set also tests whether the result holds for other patch writers.
- Same processing as the main data: test-file hunks removed, duplicate patches dropped, issues need at least one
  passing and one failing patch, up to 2 passing and 2 failing patches per issue (pairs = min of the two), seed
  20261005. Patches over 30,000 characters after test hunks are removed are dropped before sampling (43 of 2,694
  unique patches, both labels) so two patches fit in one prompt.
- **After cutoff:** issues created on or after 2025-02-01. Gemma 4's model card states a pretraining cutoff of
  January 2025. 92 issues, 167 pass/fail pairs.
- **Before cutoff:** issues created before 2025-01-01 (October to December 2024), 92 of 142 eligible issues drawn
  with seed 20261005 to match the after-cutoff set's size.
- The cutoff split is defined for Gemma 4 only. The model cards of Qwen3.5-9B and GLM-4.7-flash state no cutoff,
  and gpt-oss-20b was released 2025-08-05, so for those three the after-cutoff set is reported as "issues from
  2025" and not called unseen.

## Conditions, models, decoding

Identical to the same-conditions comparison (`scripts/selfjudge_matrix.py`): rating answer only (PASS/FAIL), rating
reasoning first (0–100), comparison answer only, comparison reasoning first, both orders; same prompts; temperature
0; output limit 8 tokens (answer only) and 3,000 tokens (reasoning first); gpt-oss at reasoning effort "low" with
3,000 extra tokens. Models: Gemma 4 31B, gpt-oss-20b, Qwen3.5-9B, GLM-4.7-flash through OpenRouter, provider
recorded per call. Reasoning-first calls without a parsed answer are asked once more (`--redo-unparsed`).

## What will be reported

For each model and each set: pair accuracy in the four conditions, tie rates, accuracy on untied pairs, order
effects, and the difference comparison minus rating (reasoning first) with a 95% interval from 2,000 bootstrap
resamples of issues. For Gemma: the change in pair accuracy from the before set to the after set, per condition,
with a bootstrap interval (issues resampled within each set).

Reading rule, fixed now: claim 1 holds on new issues for a model if the reasoning-first difference (comparison minus
rating) has an interval that includes 0 or favors rating. Remembered fixes would show as higher accuracy on the
before set than on the after set. The result is reported whichever way it falls.

## Outputs

- Rows: `scripts/derived/selfjudge_live-after_<model>.jsonl`, `scripts/derived/selfjudge_live-before_<model>.jsonl`.
- Summary `scripts/derived/post_cutoff_summary_<date>.json`; W&B group `post-cutoff-test`.
- Run log in `changelog/<date>.md` under "Run log: before/after cutoff test".

## Cost estimate

About 2,670 calls and 7.1M prompt tokens per model. At list prices about $3 for all four models; up to about $6 if
providers price above list.
