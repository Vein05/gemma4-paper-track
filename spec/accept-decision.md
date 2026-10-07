# Spec: accepting Gemma 4's own patches without review

Written 2026-10-06 before this analysis was computed. **Exploratory in one respect:** the checks compared below were
chosen after their AUROCs on Gemma's patches had been seen (`spec/outside-judge-check.md`). The decision rule, the
acceptance rates and the measures are fixed here. Terms follow `GLOSSARY.md`. No model calls; no cost.

## Question

An agent built on Gemma 4 31B must decide, for each finished patch, whether to submit it without review or to send
it to a person. If the agent accepts a fixed share of its patches, how many of the accepted ones pass, depending on
which check ranks them?

## Data

Gemma's own patches on the held-out issues scored by all nine judges (`fresh_judging.load`, runs main-a and main-b;
the patch set of `derived/fresh_replication_2026-10-06.json`). Labels as there. Secondary, reported beside it: the
same table on the Mini issues, matched-harness and mixed-harness patches (`outside_judge_check.py` patch sets).

## Checks

1. Gemma's own score.
2. Gemma plus Qwen3.5-9B: mean of the two judges' percentile ranks (as in `outside_judge_check.py`).
3. GLM-4.5's score.
4. Kimi-K2's score.

## Decision rule and measures

- The agent accepts the share a of its patches that the check ranks highest, for a = 25%, 50% and 75%. Patches tied
  at the cut are accepted at random, so a tied group contributes its pass rate in proportion to the share of it that
  is accepted (the expectation over random tie-breaks).
- Measures at each a: **precision**, the share of accepted patches that pass; and **failing patches accepted**, the
  share of all failing patches that are accepted. Base rate: the share of all patches that pass.
- Gemma's own cut: accepting every patch Gemma scores 100, with its acceptance rate and precision.
- Each check's precision minus Gemma's at each a, 95% interval from 2,000 resamples of issues (seed 0).

## Reading

A check is a better filter at a given acceptance rate if the lower bound of its precision difference from Gemma is
above 0. The paper reports the held-out table with the base rate and states that the checks were chosen after their
AUROCs were seen.
