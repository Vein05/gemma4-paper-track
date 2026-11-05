# Spec: do other models share Gemma's blind spot? (LiveCodeBench model sweep data)

Written 2026-11-03, after the sweep's leniency results were read but before any number below was computed. No new
model calls: the sweep's existing scores only. Exploratory.

## Question

For Gemma, the evidence says the trust follows the wrong fix, not the author: Gemma believes its wrong code is right and
approves code that makes the same mistake whoever wrote it. Is that also how the other flagged models fail? Two
measures per judge model M:

1. **Shared blind spot.** When M's own program for a problem fails, does M trust *other writers'* failing programs on
   that problem more than when M's own program passes? Measured as excess trust E = M's score minus Qwen3-32B's score,
   on other writers' failing programs: mean E on problems M failed minus mean E on problems M passed. Problems M fails
   are harder, so the same split is computed with every other model's pass/fail as a placebo (same kind of hard
   problems, not M's own mistakes). **Blind-spot effect = M's own split minus the mean of the placebo splits.**
2. **Own program against other wrong programs on the same problem.** On problems where M failed and other writers also
   failed: mean over problems of (E on M's own failing program minus mean E on the other writers' failing programs).

## Data and choices

- Judges: Gemma 4 31B (existing scores `scripts/derived/lcb_gemma4-31b.jsonl`; its own programs are the existing
  Gemma 4 31B programs), Gemma 4 12B, Gemma 4 26B-A4B, gpt-oss-20b, OLMo-3.1-32B, Nemotron-Nano-9B-v2, Seed-OSS-36B.
  Left out: GLM-4-9B (passes 1 of 292, 121 of 839 judgments parsed) and Phi-4-mini (passes 8 problems).
- Other writers: Gemma 4 31B, Claude 3.5 Sonnet, DeepSeek-V3 programs, leaving out M's family (Gemma models compare
  against Claude 3.5 Sonnet and DeepSeek-V3 only). Placebo splitters: the other six judges in the list above.
- Problems: the 292 judged problems. A judge needs at least 30 other-writer failing programs on each side of its split,
  else "too few".
- Interval: 95%, 2,000 problem resamples, seed 0.

## Reading, fixed now

- Blind spot for M: effect interval above 0.
- Own beyond other wrong programs: measure 2 interval above 0.
- Prediction for Gemma 4 31B from the SWE-bench evidence: blind spot present. If most flagged models show it too, the
  paper's explanation (a self-consistent wrong belief) is general, not Gemma's.

Script `scripts/lcb_blind_spot.py` → `scripts/derived/lcb_blind_spot_2026-11-03.json`.
