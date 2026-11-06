# Spec: is the repair result stable across runs?

Written 2026-11-06, before any of these runs. The user asked for "a seed of 3" and then "if nothing works just work on the
seed". A review named the repair's one run per patch as a limit. Exploratory: the held-out issues have been inspected many
times, and this set of patches produced the first result. Terms follow `GLOSSARY.md`.

## Question

The repair with the failing tests shown beat a second look, 14 against 6 of 26 blocked failing patches (8 issues against 0,
one run per patch, temperature 0). Does this hold when each patch gets other runs?

## Runs

The same 35 blocked patches, the same two arms, the same code and limits as `spec/test-repair.md` (`data` from
`$E/test-repair/run1/jobs.jsonl`), with one change: temperature 0.3 and vLLM's per-request seed set to 1 and then 2. At
temperature 0 a second run would repeat the first apart from batching noise. 0.3 is chosen as low enough to keep the model's
behaviour close to the first run and high enough to give other runs. It is not tuned, and no other value will be tried.
vLLM gets 0.70 of GPU memory, which changes speed only.

Graded with `scripts/eval_apptainer.py` against SWE-bench Verified. A run with no submission keeps the start patch's grade.

## Measures and reading, fixed now

Analysis: `scripts/repair_seeds.py`.

1. Per seed: blocked failing patches passing after repair, per arm; blocked passing patches failing, per arm; the sign test
   of `spec/test-repair.md`.
2. **Primary.** Across the two new seeds, per blocked failing patch, the number of passes with the tests shown minus the
   number with a second look; exact one-sided sign test on patches with a non-zero difference.
   - **The failing tests help across runs:** more passes with the tests shown in both seeds, and primary p < 0.05.
   - **Mixed:** more passes with the tests shown in only one seed, or p ≥ 0.05.
   - **Does not hold:** a second look repairs at least as many in both seeds.
3. Spread: for each patch and arm, the passes out of 3 runs (temperature 0 and the two seeds), and the number of patches that
   pass in all 3, some, or none. The paper's 14 is described by this spread.

The temperature 0 run is shown beside the seeds and left out of the primary test, because it chose this question.

## Prediction, written before the runs (judgment, not evidence)

More passes with the tests shown in both seeds: about 75%. Primary p < 0.05: about 60%. Passes with the tests shown per seed:
10 to 14 of 26; with a second look: 4 to 8. Some of the original 8-to-0 margin is expected to shrink.

## Run and logging

`scripts/lab/test_repair_chain.sh`, `OUT=seed1` and `OUT=seed2`, jobs copied from `run1`. W&B group `repair-seeds`, logged from
the Mac; changelog with start, end and GPU-hours; compute ledger updated; outputs in `data/lab-runs/repair-seeds/`.
