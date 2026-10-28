# Spec: do the other five models rubber-stamp their own patches on the held-out issues?

Written 2026-10-22, before any of these numbers were computed. Terms follow `GLOSSARY.md`. No model calls; existing
data only (`scripts/derived/fresh_*.jsonl`, runs `main-a` and `main-b`, 957 patches scored by all nine judges).

## Why

The paper's "only Gemma" control (Section 3.4) uses the Mini issues, where each of the five other writers has 14 to 24
failing patches. On the held-out issues all nine judges also scored the five writers' 777 patches, so each writer
judged its own patches there too: about 79 failing patches per writer. This was never computed. A rubric judge named
it as the largest gap in Quality.

Already seen: only Gemma's rows of `fresh_replication_2026-10-06.json` and the pooled other-writer numbers in it
(others' failing patches scored 100: 35%). The per-judge AUROC-by-writer table in that file holds each judge's AUROC on
each writer's patches; it has not been read for this question.

## Measures (the same definitions as the Mini analysis)

For each of the five writers W that is also a judge (Qwen3-Coder, gpt-oss-120b, GLM-4.5, Kimi-K2, Llama-4-Maverick),
on the held-out patches scored by all nine judges, with Gemma's row computed the same way as a check:

- Self-judging gap: `pair_measures` of `scripts/self_judging_replication.py` (W's AUROC drop from other writers' patches
  to its own, minus the mean drop of judges outside W's family, each outside judge's own patches left out).
- Leniency difference on failing and passing patches, and the share of own and other writers' failing patches scored
  100: `lenient` and `measures` of `scripts/other_models_leniency.py`.
- 95% intervals and 99% Bonferroni intervals (five tests) from 2,000 bootstrap resamples of issues, seed 0, the same
  resamples for every writer. Pooled over the five: mean gap and mean leniency difference, 95% intervals.

## Validity check (stop if it fails)

Gemma's row must reproduce the published held-out numbers: gap +0.074 and failing leniency difference +16.6. If not,
the reuse of the Mini code on held-out data is wrong; fix it before reading the five writers.

## Reading rule

A writer rubber-stamps like Gemma if its failing leniency difference has a 99% Bonferroni interval above zero. A writer
shows a ranking gap if its gap has a 99% Bonferroni interval above zero. Every reading is exploratory in the paper's
sense: it was chosen after the Mini result and the 2026-10-22 rubric review were seen. Report the result whichever way
it goes; if a writer passes either rule, Section 3.4's "only Gemma" sentence and the abstract change.

## Addendum (2026-10-22, after the per-writer results were seen)

Added Gemma minus the pooled five, for the gap and the failing leniency difference, with 95% intervals from the same
resamples, as `scripts/other_models_leniency.py` does on the Mini issues. Exploratory.
