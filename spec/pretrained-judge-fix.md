# Spec: judge Gemma's patches with the pretrained Gemma, confirmed on SWE-bench Lite

Written 2026-11-02, before any Lite score from either model was computed. Exploratory follow-up; it could change the
paper's story to "a fix and its mechanism" if it holds. Background: `spec/base-vs-instruct.md`,
`spec/post-training-familiarity.md`, and their results in `changelog/2026-11-02.md`.

## Why this fix

Three results from 2026-11-02 locate the rubber-stamping in Gemma's post-training: the pretrained Gemma 4 31B shows no
extra trust in Gemma's failing patches (+0.2 percentile points, against +10.0 for the instruction-tuned model); another
family's post-training (OLMo 3 32B) does not produce it (Gemma minus OLMo +7.5 [+2.2, +12.8]); familiarity with the
patch text does not explain it. So the fix to test is the simplest one that follows: score Gemma's patches with the
pretrained checkpoint, which Google releases next to the instruction-tuned one, in the plain few-shot format, and read
P("100").

## What the held-out issues already show (development data, seen before this spec)

On the 180 own patches of the held-out issues (53% pass), from the existing score files:

| Judge | AUROC, own patches | Own failing approved | Own passing approved | Precision of approval |
|---|---|---|---|---|
| Paper's judge: instruction-tuned, explains, written 100 | 0.622 | 61% | 85% | 61% |
| Instruction-tuned, plain few-shot, P("100") > 0.5 | 0.736 | 59% | 83% | 61% |
| Pretrained, plain few-shot, P("100") > 0.5 | 0.762 | 16% | 58% | 80% |

Leniency: pretrained +0.2, instruction-tuned +10.0. These numbers chose the fix, so they cannot confirm it. The cut-off
of 0.5 is the natural midpoint and was not tuned; it is fixed now.

## Confirmation set

SWE-bench Lite, another team's Gemma 4 31B run plus four leaderboard writers (`data/public/third-party-lite/patches.jsonl`,
1,478 patches; Gemma's 299, 133 failing). The four worked examples in the prompt are Lite patches, so their four
issues (`django__django-16046`, `pallets__flask-4045`, `sympy__sympy-21614`, `django__django-15061`) are removed for
every writer. Kept: patches with a parsed written score from Gemma in `scripts/derived/lite_gemma4-31b.jsonl`, so the
comparison with the paper's judge uses the same patches.

## Runs

The plain-text prompt of `spec/base-vs-instruct.md` (same four examples, same system line and question; Lite prompts
from `data/judge-prompts/lite_p1.jsonl`), built by `python base_vs_instruct.py build --set lite`. Scored on the lab A100
by `probe_extract.py plain` with the pretrained and the bf16 instruction-tuned Gemma 4 31B. About 1,470 patches per
model, about 45 minutes each. No pilot: the format passed on the held-out issues for both models.

## Measures

Intervals: 95%, 2,000 resamples of Lite issues, seed 0.

1. Leniency L for each model (percentile of log P("100") among the Lite set; own failing minus other writers' failing
   on the same issue, averaged over issues), and D = L(instruction-tuned) − L(pretrained).
2. Ranking: AUROC on Gemma's own patches for the pretrained model's P("100"), minus the AUROC of Gemma's written score
   (the paper's judge) on the same patches. Also reported for the instruction-tuned P("100").
3. Approval at P("100") > 0.5 by the pretrained model: share of own failing patches approved, own passing approved,
   and precision of approval on own patches; the same for the written score of 100 (paper) and for other writers'
   patches.

## Reading, fixed now

- **Fix confirmed, better ranking too:** L(pretrained)'s interval includes 0 or is below 0, D's interval is above 0, and
  the interval of the AUROC difference (pretrained minus written) is above 0.
- **Fix confirmed:** the same, except the AUROC difference's interval includes 0 with its lower end above −0.05.
- **Bias removed, ranking lost:** the L conditions hold and the AUROC difference's lower end is at or below −0.05.
- **Not confirmed:** L(pretrained)'s interval is above 0, or D's interval includes 0.
- Approval shares (measure 3) are reported beside the reading, never alone.

## Logging

Score files to `data/lab-runs/pretrained-judge-fix/`; analysis `python pretrained_judge_fix.py` →
`scripts/derived/pretrained_judge_fix_2026-11-02.json`; W&B group `base-vs-instruct`; changelog entry.

## Addendum 1 (2026-11-02, before any Lite score)

The user pointed out that the pretrained model approves only 58% of Gemma's passing held-out patches at P("100") > 0.5,
against 85% for the paper's judge. At matched approval of passing patches, the held-out gain splits in two: the plain
format makes the score adjustable (both models gain about equally on ranking Gemma's own patches), and only the
pretrained model removes the extra trust in Gemma's failing patches. Two numbers are added to the report so that the
Lite run shows which change does what. Both are reported only; the reading rule above is unchanged.

4. Ranking, pretrained minus instruction-tuned, both in the plain format: the AUROC difference on Gemma's own patches,
   with its interval.
5. Matched approval: for each of the three judges (paper's written score, instruction-tuned P("100"), pretrained
   P("100")), the share of Gemma's failing patches approved when the cut-off approves 85%, 70% and 58% of Gemma's
   passing patches (the cut-off is the matching quantile of that judge's scores on passing patches; the written score
   is reported only at the share its 100 gives).
