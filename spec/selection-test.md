# Spec: selection test (CHARTER claim 2)

Written 2026-10-05, before any selection data was collected. Terms follow `../GLOSSARY.md`.

## Question

When a model has to choose one patch out of several attempts at the same issue, does a pointwise rating choose as
well as pairwise comparison, and how many model calls does each need?

## Data and pools

- Source: public `nebius/SWE-agent-trajectories` pages cached in the session scratchpad (rows 0–3,899), loaded with
  `api_quickcheck.load` (unique patches per issue, test-file hunks removed, hidden-test outcome per patch).
- Pool per issue: 1 passing patch and 3 failing patches, drawn with seed 20261005 from the issue's unique patches.
  Issues need at least 1 passing and 3 failing patches: 42 issues qualify. Random choice is right 25% of the time.
- Limitation stated in the paper: real agents' pools have varying numbers of passing patches; this design measures
  the ability to find the one working patch, which is the hardest useful case.

## Selection methods (all on the same pools)

| Method | How the patch is chosen | Model calls per pool |
|---|---|---|
| Random | uniform | 0 |
| Rating, answer only | PASS/FAIL per patch; choose among PASS (or among all if none) | 4 |
| Rating, reasoning first | 0–100 score per patch at temperature 0; highest score | 4 |
| Averaged rating | mean of 3 reasoning-first scores per patch sampled at temperature 0.7; highest mean | 12 |
| Comparison, answer only | every pair of the 4 patches in both orders (12 calls); most wins | 12 |
| Comparison, reasoning first | as above with reasoning first | 12 |
| Rating, then comparison among tied | reasoning-first rating; if several patches share the top score, reasoning-first comparisons (both orders) among those only; most wins | 4 + 2·(tied pairs) |

Ties in any final choice are broken uniformly at random, scored by expectation (a tie among t patches containing
the passing one counts 1/t). Comparison wins count each order separately, so a pool has 12 votes.

## Measures

- Selection accuracy: share of pools where the chosen patch passes the hidden tests (expected value under random
  tie-breaking).
- Model calls per pool, and output tokens per pool where the provider reports them.
- Tie rate at the top for each rating method.
- Paired differences between methods on the same pools; 95% intervals from 2,000 bootstrap resamples of issues.

## Models and decoding

Gemma 4 31B, gpt-oss-20b, Qwen3.5-9B, GLM-4.7-flash through OpenRouter, default provider routing, provider recorded
per call. Prompts identical to `scripts/selfjudge_matrix.py` (rating and comparison, answer only and reasoning first).
Temperature 0 except the averaged rating (0.7). Output limits 8 tokens (answer only) and 3,000 (reasoning first);
gpt-oss runs at reasoning effort "low" with 3,000 extra tokens. Ratings at temperature 0 already collected for the
same patch, prompt and model in `derived/selfjudge_*.jsonl` are reused, not re-asked; every reuse is marked in the
output rows.

## What will be reported

For each model: selection accuracy and calls per pool for every method, and the paired difference between each
rating method and reasoning-first comparison with its interval. Claim 2 is supported for a model if a rating method
(averaged rating, or rating then comparison among tied) is within 0.05 of reasoning-first comparison, with the
interval of the difference excluding −0.10, at fewer calls. The result is reported whichever way it falls.

## Outputs

- Script: `scripts/selection_test.py` (`run`, `analyze`).
- Rows: `scripts/derived/selection_<model>.jsonl` (one row per model call); summary
  `scripts/derived/selection_summary_<date>.json`; W&B group `selection-test`.
- Every run, change and problem is logged in `changelog/<date>.md` under a "Run log: selection test" heading.

## Cost estimate

About 40 new calls per pool per model (12 averaged-rating samples, 24 comparisons, ratings for patches not yet
rated). 42 pools × 4 models ≈ 6,700 calls; estimated $4–6 in total, most of it Gemma's reasoning-first calls.

## Correction, 2026-10-05 (before the runs started)

Dry run: 42 pools, each exactly 1 passing + 3 failing patches; 1,848 calls per model, of which 88–96 ratings and 28–32
comparisons are reused from the same-conditions runs, leaving about 1,720 new calls per model (6,900 total). Cost
re-estimated from Gemma's earlier spend per reasoning-first call: about $7 in total (Gemma about $5). Unparsed answers:
an unparsed rating counts as the lowest score (never preferred over a parsed one); an unparsed comparison casts no vote.
