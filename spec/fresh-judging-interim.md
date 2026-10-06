# Spec: interim check of the self-judging gap on the first 100 fresh issues, three judges

Written 2026-10-06 before any judge call on the fresh patches. Exploratory: it does not replace or count as the
primary analysis of `spec/fresh-replication.md`, which still needs all nine judges. Its only use is to decide
whether to buy credit for the full judging; that decision is reported with its result.

## Why

OpenRouter credit is $1.34 and the full judging costs about $8. The user wants a cheap first look at whether
Gemma 4's own-patch gap appears on patches written in mini-SWE-agent before paying for the rest.

## Patches

- Issues: positions 0–99 of the fixed order (`runs/main-a`, graded), kept only where the reference patch resolves on
  Magnolia (spec addendum) and Gemma's patch has a label (`graded` or `patch_apply_failed`).
- Gemma: its non-empty patches from `runs/main-a/preds.jsonl`; labels from Magnolia (`labels.jsonl`).
- Control: the five control writers' patches on the same issues
  (`data/public/swe-bench-verified-control-fresh/attempts.jsonl`, official labels).
- Same preprocessing as `scripts/self_preference.py`: test files stripped, patches over 30,000 characters left out.

## Judges and prompt

Gemma 4 31B (`google/gemma-4-31b-it`), gpt-oss-120b (`openai/gpt-oss-120b`) and Qwen3.5-9B (`qwen/qwen3.5-9b`), the
cheapest outside judges of the nine. Same prompt (`Q_P1`), settings (temperature 0, reasoning off, 3,000 tokens) and
parser as `spec/self-judging-replication.md`, through `scripts/fresh_judging.py` (which reuses its functions).
Unparsed answers are asked once more, then left out.

## Measures

- Gemma's self-judging gap as in `scripts/self_judging_replication.py`, with two outside judges instead of eight:
  (Gemma's AUROC on control patches − on its own) − mean over outside judges of the same difference (an outside judge
  that wrote control patches has those left out of its control set). 95% interval from 2,000 bootstrap resamples of
  issues.
- Patch-matched leniency, raw and rank-normalised, as in the 2026-10-06 12:05 addendum to
  `spec/fresh-replication.md` (added after that spec's freeze; reported as such).
- Rubber-stamp rate: share of Gemma's own failing patches it scores 100, vs control writers' failing patches.
- Reading: none is fixed. With two outside judges and about 100 issues the interval will be wide; the result is
  described, not tested. The original gap was +0.135 [0.060, 0.210] against eight outside judges.

## Cost and stopping

About 550 patches × 3 judges; at the earlier per-call costs about $0.45. Stop if spend passes $1.00.
W&B project `gemma4-paper-track`, group `fresh-judging-interim`.
