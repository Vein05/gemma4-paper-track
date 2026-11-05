# Spec: does post-training create rubber-stamping? Pretrained vs instruction-tuned Gemma 4 31B

Written 2026-11-02, before any score from either model was computed. Approved by the user the same day (chat: "I
think this is much more interesting, create a doc on this, and start the download"). Exploratory follow-up to the
paper, not part of its frozen plans. Background: `handoff/2026-11-02.md` (the probability of the 100) and
`spec/judge-probe.md` (the teacher-forced score method this spec reuses).

## Question

Gemma 4 31B gives 100 to 61% of its own failing held-out patches and rates its own failing patches higher than
other writers' failing patches on the same issues. The Gemma team controls two training stages: pretraining and
post-training (instruction tuning and preference training). Which stage produces this leniency?

The test: give the pretrained model (`google/gemma-4-31B`) and the instruction-tuned model built from it
(`google/gemma-4-31B-it`; its model card lists `google/gemma-4-31B` as the base model) the same patches in the same
prompt, and compare how each ranks Gemma's own failing patches against other writers' failing patches.

Why a Gemma engineer would care, by outcome:

| Outcome | What it says about their pipeline |
|---|---|
| Pretrained model not lenient on own failing patches, instruction-tuned model lenient | Post-training creates it; the cause is in post-training data or objectives |
| Both lenient by a similar amount | It is there before post-training; a judge-specific fix (for example, fine-tuning on verified labels) is the right kind of remedy |
| Pretrained model more lenient | Post-training already reduces it, and the released model keeps the remainder |

## Models

Both in full 16-bit weights (bf16), downloaded from Hugging Face on 2026-11-02 to
`<workdir>/gemma4-paper-track/models/gemma-4-31B` and `.../gemma-4-31B-it` on the lab A100. Using the
full-weight instruction-tuned model, not the 4-bit competition checkpoint, keeps precision equal across the
two. The 4-bit checkpoint (`gemma-4-31B-it-qat-w4a16-ct`, which wrote the patches) is scored a third time with the
same prompt as a check that precision does not change the instruction-tuned result.

"Own" means patches written by the 4-bit instruction-tuned model. For the pretrained model these are patches written
by its own descendant; the comparison is between training stages of one model, not between self and stranger.

## Patches and labels

The 957 held-out patches scored by all nine original judges, as in `spec/judge-probe.md`: 180 of Gemma's own
(85 failing), 777 by five other writers. Labels: SWE-bench resolved, as in the paper.

## Prompt and read-out

A pretrained model does not follow chat turns or write an explanation and then a score, so both models get the
identical plain-text prompt (no chat template, beginning-of-sequence token added):

1. Four worked examples, then the patch to score. Each example is the paper's judging text (system line, issue,
   patch, question) followed directly by `SCORE: 100` (patch passed) or `SCORE: 0` (patch failed). The examples
   are SWE-bench Lite patches by other writers (`data/public/third-party-lite/patches.jsonl`, writer not Gemma,
   issue not among the held-out issues): the two shortest passing and the two shortest failing by issue plus patch
   length, in the order pass, fail, pass, fail. The file of examples is saved before scoring.
2. The patch to score in the same format, ending with `SCORE: ` and no explanation.
3. Read-out: log P("100") after `SCORE: `, teacher-forced (the same code as `probe_extract.py score`, with a new
   plain-text option). One forward pass per patch, no sampling.

Both models skip the explanation, so this is not the paper's setting (explain, then score). The instruction-tuned
model's usual setting is reported beside it from existing data: P(100) after its own explanation (local 4-bit model,
`data/lab-runs/probe/score_local/`).

## Pilot (format check only)

20 own and 20 other-writer patches, half failing. The pilot prints only format checks, not ranking results: for each
model, the median total probability that the token after `SCORE: ` is a digit, and the median log P("100"). Pass:
the median digit probability is at least 0.5 for both models. If the pretrained model fails, change the prompt once
(for example, eight examples instead of four), record the change in an addendum, and repeat the pilot. The pilot
patches stay in the main run.

## Measures

For each model, convert log P("100") to a percentile rank (0 to 100) among that model's scores on all 957 patches.
Percentiles remove differences in how sharp each model's probabilities are.

1. **Leniency (primary).** For each held-out issue with at least one own failing patch and one other-writer failing
   patch: the own failing patch's percentile minus the mean percentile of the other writers' failing patches.
   Averaged over those issues. L(pretrained), L(instruction-tuned), and their difference
   D = L(instruction-tuned) − L(pretrained).
2. **Own-patch ranking (secondary).** AUROC of log P("100") on own patches, on other writers' patches, and the gap
   (others minus own), per model.
3. **Descriptive.** Share of own failing patches whose P("100") is above 0.5, per model; the same for other writers'
   failing patches.

Intervals: 95%, 2,000 resamples of issues, seed 0.

## Reading, fixed now

- **Post-training creates it:** D's interval is above 0 and L(pretrained)'s interval includes 0.
- **Post-training adds to it:** D's interval is above 0 and L(pretrained)'s interval is above 0.
- **Present before post-training:** D's interval includes 0 and both L intervals are above 0.
- **Post-training reduces it:** D's interval is below 0.
- Any other pattern is inconclusive.

The 4-bit check: if L for the 4-bit instruction-tuned model differs from the bf16 one by more than half of D, the
paper must report both and say precision matters.

## What could go wrong

- The few-shot format may not match the paper's leniency: the instruction-tuned model's leniency in this format is
  itself a result. If L(instruction-tuned) here is not above 0, the format has removed the effect and the comparison
  says nothing about the paper's finding. Report that plainly.
- Four examples with 100 and 0 set the scale. Changing them could shift both models; it should not change their
  ranking of patches much. Not tested unless the pilot fails.
- Long prompts: the four examples add a few thousand tokens. Patches whose full prompt exceeds 32,768 tokens are left
  out and counted.

## Cost and logging

About 125 GB of downloads (two models). Scoring: one forward pass per patch per model, about 1,000 patches times
three models; roughly one to two hours each on the A100 (guess). No API spend. W&B group `base-vs-instruct`;
changelog entry in `changelog/2026-11-02.md`.
