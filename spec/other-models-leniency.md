# Spec: are the other five models lenient on their own failing patches? (intervals)

Written 2026-10-22, before the intervals were computed. Terms follow `GLOSSARY.md`. No model calls; existing data only.

## Why

The writeup (Section 3.3) can say only that the other five self pairs' leniency point estimates run from −5.4 to +17.5
"without intervals". Llama-4-Maverick's +17.5 is close to Gemma's +20.9 on the same patch set. A reader will ask whether
rubber-stamping (as opposed to the ranking gap) is specific to Gemma. This test adds intervals.

Already seen before writing this spec: the point estimates in `derived/self_judging_replication_2026-10-05.json`
(leniency difference: Qwen3-Coder +4.1, gpt-oss-120b +2.1, GLM-4.5 +7.1, Kimi-K2 −5.4, Llama-4-Maverick +17.5; Gemma
+20.9) and the share of own failing patches scored 95 or above. The intervals, the pooled estimate and the share scored
exactly 100 have not been computed.

## Data (no new data)

The Mini issues, mixed-harness patch set used by `scripts/self_judging_replication.py`: 333 patches scored by all nine
judges (50 issues). Five self pairs (judge = the model that wrote one control writer's mini-SWE-agent patches) plus
Gemma 4 31B for reference. Own failing patches per pair: 14 to 24 (Gemma 80).

## Measures (fixed now)

Same definitions as `scripts/self_judging_replication.py`, `leniency()`:

- Leniency of judge J on patch i: J's score minus the mean of the outside judges' scores on i (outside judges exclude J,
  J's writer's family and the family of patch i's writer).
- **Leniency difference** for J: mean leniency on J's own failing patches minus mean leniency on other writers' failing
  patches.
- Secondary: the same difference on passing patches; rubber-stamp rate (share of own failing patches scored exactly
  100) against the share of other writers' failing patches scored 100.
- **Pooled leniency difference**: mean of the five non-Gemma pairs' leniency differences.
- Secondary: Gemma's leniency difference minus the pooled five.

Intervals: 2,000 bootstrap resamples of issues (seed 0), the same resamples for every pair; percentile 95% intervals.
Because five pairs are tested, also a Bonferroni interval per pair (99%). Resamples where a pair has no own failing
patch are dropped for that pair (count reported).

## Reading rule (fixed now)

- A pair is called lenient on its own failing patches only if its Bonferroni (99%) interval lies above 0. A 95%
  interval above 0 without the Bonferroni one is reported as "suggestive".
- Pooled: if the 95% interval lies above 0, the other models are lenient on average and the writeup cannot call
  rubber-stamping specific to Gemma. If it includes 0, the writeup says so with the interval.
- If Llama-4-Maverick (or any pair) is lenient by the rule above, the writeup must say so in Section 3.3 and narrow the
  "only Gemma" claim to the ranking gap.
- Per-pair results are low power (14 to 24 failing patches); a wide interval that includes 0 is "not shown", not
  "absent".

## Outputs

`scripts/other_models_leniency.py` → `scripts/derived/other_models_leniency_2026-10-22.json`; W&B group
`self-judging-replication` (run `other-models-leniency-2026-10-22`); entry in `changelog/2026-10-22.md`.

## Result (added 2026-10-22, after the run)

`scripts/derived/other_models_leniency_2026-10-22.json`; W&B group `self-judging-replication`, runs
`other-models-leniency-2026-10-22-*`. Gemma's row reproduces the writeup (+20.9 [11.5, 30.2], 49 of 80 scored 100), so
the script matches the earlier computation. No resample was dropped.

| Self pair | Own failing | Leniency difference, failing [95%] | Bonferroni 99% | Own / others' failing scored 100 |
|---|---|---|---|---|
| Qwen3-Coder | 15 | +4.1 [−6.1, 14.6] | [−8.2, 18.3] | 7% / 0% |
| gpt-oss-120b | 24 | +2.1 [−9.1, 13.0] | [−11.3, 15.6] | 0% / 0% |
| GLM-4.5 | 14 | +7.1 [−10.5, 26.3] | [−17.7, 31.6] | 7% / 16% |
| Kimi-K2 | 14 | −5.4 [−17.6, 7.2] | [−22.1, 11.6] | 0% / 2% |
| Llama-4-Maverick | 21 | +17.5 [0.6, 32.9] | [−3.5, 38.4] | 43% / 40% |
| Gemma 4 31B (reference) | 80 | +20.9 [11.5, 30.2] | [8.4, 32.6] | 61% / 20% |

- Pooled over the five: +5.1 [−0.8, 11.0]. By the reading rule, the other models are not shown to be lenient on
  average. Gemma minus the pooled five: +15.8 [4.0, 27.7].
- Llama-4-Maverick: 95% interval above 0, Bonferroni interval includes 0, so **suggestive**, not lenient by the rule.
  It does not rubber-stamp in Gemma's sense: it gives 100 to its own failing patches about as often as to other
  writers' (43% vs 40%), because it gives high scores to most failing patches.
- No pair is lenient by the rule, so the writeup keeps "only Gemma" for both measures and replaces "without
  intervals" with these intervals.
- Secondary, passing patches: gpt-oss-120b +12.1 [5.1, 19.9] on its own passing patches (10 patches); the others'
  intervals include 0; Gemma +0.2 [−7.6, 8.7].
