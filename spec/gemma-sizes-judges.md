# Spec: other Gemma 4 sizes as judges of the held-out patches

FROZEN 2026-10-28, before any score from either size (the smoke test had not run). Drafted 2026-10-23 (todo item 4).
The user's OK for the smoke test and the full judging: 2026-10-28 ("let's do this?"). The sections "Reading rule" and
"Predictions" were added at the freeze. Terms follow `GLOSSARY.md`.

## Why

Gemma 4 31B gives the top score to 61% of its own failing held-out patches. Other models from other families do not do
this on their own patches. This run asks whether two other Gemma 4 sizes, which did not write the patches, also trust
31B's failing patches more than other writers' failing patches. If they do, the extra trust is shared by the family; if
they do not, it belongs to the model that wrote the patches. It does not separate recognising one's own patch from
sharing its mistakes, and the paper must not claim that it does. Each size's leniency on other writers' failing
patches is reported too, so a size that gives 100 to everything does not look like a family effect.

## Judges

Self-hosted on the lab A100 with vLLM 0.30.0 (the environment of `spec/multilingual-replication.md`), one model at a
time, temperature 0, thinking off:

- Gemma 4 12B: `google/gemma-4-12B-it-qat-w4a16-ct`, the same 4-bit format as the 31B checkpoint that wrote the
  patches.
- Gemma 4 26B-A4B: `google/gemma-4-26B-A4B-it` (bf16 weights) served with vLLM's fp8 quantization. Google publishes
  no w4a16 checkpoint of it, and bf16 (about 52 GB) does not fit beside the other user's jobs.
- Revisions are pinned at download and recorded in `run.json`.

## Patches, prompt and parser

- The held-out patches the 31B judge scored (`scripts/derived/fresh_gemma4-31b.jsonl`; 180 of Gemma's and 777 of
  other writers' are scored by all nine judges).
- The held-out prompt exactly (`fresh_judging.patches` and `selection_test.rating_prompt` with `Q_P1`, the system
  message of `selfjudge_matrix.call`), 3,000 output tokens, unparsed answers asked once more with 8,000, parser
  `selfjudge_matrix.parse("P1", ...)`.
- Rows in `scripts/derived/fresh_<tag>.jsonl` with the same fields as the OpenRouter judges, `provider` set to
  `local-vllm`.

## Measures (fixed before any score)

For each size, on the patches scored by all nine judges and the new size, with the eight outside judges as in the
paper:

1. Share of 31B's own failing patches scored 100, beside the share of other writers' failing patches scored 100.
2. Leniency on 31B's failing patches minus leniency on other writers' failing patches, 95% interval from 2,000
   bootstrap resamples of issues.
3. Leniency on other writers' failing patches alone.
4. AUROC on 31B's patches and on other writers' patches.

## Smoke test

20 prompts per size (10 of Gemma's patches, 10 of other writers'). Checks: the server starts in the memory free on the
shared GPU, answers parse, no thinking tokens, time per call.

## Analysis

`scripts/gemma_sizes_analysis.py --sizes gemma4-12b,gemma4-26b-a4b` on the held-out runs (`main-a`, `main-b`). It uses
`fresh_judging.load`, so a patch enters only if all nine paper judges and every given size scored it, and a re-asked
answer replaces the unparsed one. Outside judges are the paper's eight non-Gemma judges, minus the family of each
patch's writer. Leniency is a judge's score minus the outside judges' mean on the same patch. 95% intervals come from
2,000 bootstrap resamples of issues (seed 0). Before any size was run, the script with no sizes reproduced the paper's
31B numbers: leniency difference on failing patches +16.6 [10.3, 23.1], on passing patches +3.4 [−2.0, 8.0], AUROC
0.622 (own) and 0.751 (other writers'), 52 of 85 own failing patches and 136 of 393 other writers' failing patches
scored 100, 957 patches. If a size drops patches from the set, 31B is reported on the smaller set too.

## Reading rule

Each size is read on its own. "Leniency difference" is measure 2: leniency on 31B's failing patches minus leniency on
other writers' failing patches.

- Validity first. A size is read only if at least 95% of its prompts parse after the one re-ask, no answer carries
  thinking tokens, and its AUROC on other writers' patches is at least 0.60. A size that fails this is reported as too
  weak to judge, with its numbers in the supplement only.
- **Shares the extra trust:** the size's leniency difference has a 95% interval with lower bound above 0.
- **Does not share it:** the interval includes 0 and its upper bound is below +8.3, half of 31B's +16.6.
- **Inconclusive:** anything else.
- **Weaker than in 31B:** the paired difference "31B's leniency difference minus the size's" has a lower bound above 0.
- "The Gemma family shares it" may be written only if both sizes meet "shares the extra trust". If one size does, the
  paper names that size.
- Whatever the outcome, the paper does not say whether a size recognises 31B's patches or shares their mistakes. The
  share scored 100 (measure 1) is reported beside measure 2, never alone.

## Predictions (written at the freeze, before any score)

- Gemma 4 12B: gives 100 to about 65% of 31B's failing patches and 45% of other writers' failing patches; leniency
  difference about +8 points with an interval about ±10 wide; lower bound above 0 with probability about 0.4. AUROC on
  other writers' patches about 0.68; it fails the validity check with probability about 0.15.
- Gemma 4 26B-A4B: 60% and 40%; leniency difference about +8; lower bound above 0 with probability about 0.5. AUROC
  on other writers' patches about 0.72.
- Both sizes meet "shares the extra trust": probability about 0.25. Neither does: about 0.4.
