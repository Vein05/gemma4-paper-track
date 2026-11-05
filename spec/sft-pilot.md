# Spec: can a small LoRA adapter trained on execution labels make Gemma 4 31B a better patch checker?

Written 2026-11-04, before any training or scoring run. Exploratory. **Not yet approved for the GPU**: the lab A100
needs the user's OK for each start. Plan source: `notes/method-budget-2026-11-04.md`, section "Deadline revision"
(one capped training-feasibility test, 2 to 3 A100-hours in total, 128 training examples, one epoch, one seed, one
fixed configuration). Background: `notes/method-path-review-2026-11-04.md`. Code: `scripts/sft_pilot.py`,
`scripts/lab/sft_pilot_chain.sh`. Data: `data/sft-pilot/` (`manifest.json` holds the counts and md5 sums).

This pilot is separate from the longer-term idea that a convincing wrong candidate in the verifier's context makes
its checks worse (the method review's candidate-swap proposal). Nothing here tests that idea or depends on it.

## Question

The fix list (`notes/fix-attempts-2026-11-03.md`, row 7) shows that training the judge was proposed and dropped
without a run. The frozen-model results (probes, the score's probability, the pretrained checkpoint, the judge with a
shell) say what Gemma's current weights do; they say nothing about what a weight update can do. The probe result that
Gemma's state places its own stamped failures with the passing patches is a reason to expect training to be hard,
not evidence that it cannot work.

Question: after one epoch of LoRA on 128 labelled judgments, does Gemma reject more failing patches **at the same
retention of passing patches** than the identical model with the adapter switched off? Lower approval alone does not
count: a model that says FAIL more often to everything has not learned to check.

## Data

All labelled judging prompts already in the project: the held-out issues (`data/judge-prompts/heldout_p1.jsonl`,
labels as in `fresh_judging.load`: Gemma's from Magnolia, other writers' from the official control runs; 1,010 of the
1,063 prompts have a label) and SWE-bench Lite (`lite_p1.jsonl`, labels from `third_party_lite.py build`; 1,478).
2,488 judgments on 463 issues, written by Gemma 4 31B and nine other writers. The 37 issues in both sets are one
issue each.

- **Split by issue**, never by patch: issues ordered by md5 of `sft-pilot-2026-11-04|<issue id>`; the first 40% are
  the training pool, the next 20% development, the last 40% evaluation. No issue is in two splits.

  | Split | Issues | Rows | Passing | Failing | Gemma's own | Gemma's own failing it scored 100 |
  |---|---|---|---|---|---|---|
  | Training pool | 185 | 1,013 | 457 | 556 | 192 | 60 |
  | Development | 93 | 496 | 230 | 266 | 100 | 27 |
  | Evaluation | 185 | 979 | 451 | 528 | 194 | 51 |

- **Training rows (128).** Training-pool issues that have a passing and a failing row of at most 6,144 tokens (100
  issues; 23 training-pool rows are longer, a memory limit for training only), taken in md5 order, first 64. From
  each issue: the failing row Gemma scored highest as reader (the confidently accepted near miss; ties by md5) and one
  passing row by md5. So 64 passing and 64 failing rows, each issue contributing one of each; 41 of the 64 failing
  rows got 100 from Gemma; 31 rows are Gemma's own patches, 97 come from nine other writers; 53 held-out, 75 Lite;
  mean 1,245 tokens, longest 4,535. Order shuffled with seed 0.
- Development and evaluation rows are used whole: no length filter, no truncation (longest 10,292 tokens).
- All these issues and patches were inspected earlier in the project. The result is exploratory; it cannot serve as
  an untouched confirmation.

## Answer format and score

The project's answer-only rating: the judging prompt with its last paragraph replaced by "Answer with exactly one
word: PASS or FAIL." (`Q_P0` in `selfjudge_matrix.py`), the paper's system message, Gemma's chat template with
thinking off (the generation prompt ends with an empty thought channel, as in the probe runs and vLLM). `PASS` and
`FAIL` are single tokens (38678 and 43792). The score of a row is logit(PASS) minus logit(FAIL) at the first answer
position. No text is generated.

## Model and training (fixed now, no tuning)

- Checkpoint: the paper's deployed 4-bit checkpoint `gemma-4-31B-it-qat-w4a16-ct` on the lab A100, loaded with
  `CompressedTensorsConfig(run_compressed=False)`: the 4-bit weights are expanded once to bf16, so the base weights
  are exactly the deployed values (the probe runs loaded it the same way). LoRA sits on top in bf16. This replaces the
  budget note's QLoRA: re-quantizing to NF4 would change the base weights and add a loading difference to the
  comparison. If the expanded model does not fit, that is an engineering stop, not a switch to NF4 (that needs an
  addendum first).
- LoRA: rank 16, alpha 32, dropout 0.05, on the query, key, value, output, gate, up and down projections of the
  language model only (no vision tower). If expansion leaves a Linear subclass, it is swapped for a plain Linear with
  the same weight before wrapping (`plain_linears`).
- Loss: cross-entropy of the label word at the first answer position; prompt tokens carry no loss.
- AdamW, learning rate 1e-4, no weight decay, batch of one row with 4-step gradient accumulation (32 optimizer
  steps), 3 warm-up steps then linear decay to 0, gradient clipping at 1.0, gradient checkpointing, seed 0, one epoch.
  The adapter at the end of the epoch is the one evaluated; no checkpoint selection.
- Environment: `.venv-sft` on the lab (a copy of the probe environment: torch 2.13.0+cu130, transformers 5.18.0,
  compressed-tensors 0.17.0, accelerate 1.15.0; plus peft 0.21.2, installed without dependencies). Each run writes
  versions, file md5 sums and times to `run.json`.

## Conditions

1. **Adapter off** (the untuned control): the same process and loaded weights with the adapter disabled
   (`disable_adapter`), same prompt, format and score. It removes any gain from the answer format or the loader.
2. **Adapter on.**
3. References, no new runs, format differs: Gemma's written 0 to 100 score as reader (the paper's setting, hosted) and
   log P("100") of the hosted answers teacher-forced through the local checkpoint (held-out and Lite score files).
   Reported beside the two conditions; they decide nothing.

## Measures (on the evaluation split unless stated)

The threshold for each condition is fixed on the development split: the score that keeps 90% of development passing
patches (accept if score ≥ threshold). Evaluation outcomes are not looked at before this is applied.

- **Primary: false acceptance.** Share of evaluation failing patches accepted at the development threshold, adapter
  on minus adapter off; 95% interval from 2,000 bootstrap resamples of evaluation issues (both conditions on the same
  resample). Also reported: share of evaluation passing patches kept at that threshold.
- **Supporting: same-issue pair accuracy.** Over all evaluation pairs of a passing and a failing patch on the same
  issue (658 pairs on 102 issues), the share where the passing patch scores higher, ties half; on minus off, same
  bootstrap.
- Secondary: AUROC on minus off; false acceptance at the threshold that keeps 90% of evaluation passing patches (no
  transfer from development); the mean probability of PASS and the share of answers that are PASS, on failing and
  passing patches (the size of any plain shift towards FAIL).
- Slices, reported without a rule: Gemma's own patches; other writers' patches; held-out and Lite; patches Gemma
  scored 100 as reader ("stamped"), and Gemma's own stamped patches (51 failing, 97 passing in evaluation).
- The same measures on the development split, for reference.

## Reading, fixed now

- **Improves checking**: false acceptance falls by at least 10 points with the interval below 0, the adapter keeps at
  least 85% of evaluation passing patches at its development threshold, and same-issue pair accuracy rises with the
  interval above 0.
- **No measurable improvement**: both intervals (false acceptance and pair accuracy) include 0.
- Anything else is **inconclusive** (for example a fall of less than 10 points, or false acceptance falls while pair
  accuracy does not move).

What each reading allows:

- Improves checking: report it as an exploratory result on previously inspected issues. Before the word "fix" is used,
  a separate, separately approved confirmation run is needed (new issues, fixed again in a spec). Then, and only then,
  run the label-shuffled control below.
- No measurable improvement: one epoch on 128 examples did not change Gemma's checking. It does not show that more
  data, longer training, a different objective or execution-based training cannot. Finish the paper with training
  left open.
- Inconclusive: report the numbers; no further training under this budget.

**Label-shuffled control (only after "improves checking", inside the same cap).** Same rows, same settings, labels
permuted across the 128 rows with seed 1 (balance kept): `train --shuffled --name shuffled`, then
`score --adapter on=... --adapter shuffled=...` (the off and on scores are reused). It asks whether the gain needs the
labels or comes from any tuning on this format. Reported as the on-minus-shuffled difference with the same bootstrap.

Power: with 528 failing and 451 passing evaluation patches on 185 issues, a synthetic check of the analysis code gave
intervals of about ±0.045 for the false-acceptance difference and ±0.04 for pair accuracy. The real width depends on
how correlated the patches of an issue are. Gemma's own stamped failing patches number 51, too few for a rule.

## Compute, stop rules and the cap

- Throughput evidence: the probe run did 1,063 forward passes of the held-out prompts on this A100 with the same
  loading in 440 s (`notes/compute-ledger-table.md`), about 4,000 prompt tokens per second. Scoring 1,475 rows under
  two conditions is 4.8 million tokens (about 20 minutes at that rate); training is 159,000 tokens. Training speed is
  not measured yet; the smoke test measures it.
- Smoke test (`sft_pilot.py smoke`): loads the model, trains 4 optimizer steps on the 16 longest training rows,
  scores the 8 longest evaluation-or-development rows with the adapter off and on, and projects the full run from the
  measured speeds. Its rows and adapter are thrown away. Stop (no full run) if peak GPU memory exceeds 76 GB, any loss
  or score is not finite, the adapter-off model's top token is PASS or FAIL on fewer than 6 of the 8 rows, or elapsed
  time plus the projected run exceeds 90% of the cap.
- The chain stops before starting if the GPU already holds more than 2 GB (another user's job).
- Hard cap: 3 A100-hours for the whole chain (`timeout`), smoke test and both model loads included. Hitting it is an
  engineering stop: record it, do not extend the budget.
- Out of scope under this budget: more seeds, other learning rates, larger training sets, GRPO, head localization,
  new execution runs.

## Logging

Outputs on the lab in `<workdir>/gemma4-paper-track/sft/<run>/` (`run.json`, `train_log_*.jsonl`,
`scores.jsonl`, `adapter-*`, `smoke/`), copied to `data/lab-runs/sft-pilot/<run>/`. Analysis on the Mac:
`python3 scripts/sft_pilot.py analyze --scores data/lab-runs/sft-pilot/<run>/scores.jsonl >
scripts/derived/sft_pilot_<date>.json`. W&B group `sft-pilot` from the Mac (training curve from `train_log`, the
summary via `log_wandb.py`). Changelog entry with start, end and GPU-hours; the run goes into
`notes/compute-ledger.md` and `notes/compute-ledger-table.md`.

## Commands

On the lab, after the user's OK:

```
cd <workdir>/gemma4-paper-track/sft && nohup bash sft_pilot_chain.sh > logs/chain.log 2>&1 &
grep -E "START|SMOKE|TRAIN_DONE|SCORE_DONE|ALL_DONE|RUN_FAILED" logs/chain.log
```

Checked before this spec, without the GPU: the full code path (smoke, train, score with a second adapter, analysis)
on a 4-layer random Gemma 4 model on the Mac; the reloaded adapter reproduces the in-run scores exactly; the adapter-off
scores equal the plain model's; a synthetic adapter that only shifts scores towards FAIL reads "no measurable
improvement", and one that separates better reads "improves checking".

## Addendum 1 (2026-11-04, written before the second run): the corrected training run

**Why.** The first run (`changelog/2026-11-04.md`, "Capped training pilot: result" and "diagnosis") did not test
training. Gemma 4 caps its final logits at 30 (`final_logit_softcapping`). The loss was cross-entropy over the whole
vocabulary, and the adapter lowered it by raising both PASS and FAIL to the cap within four optimizer steps. The first
steps were also unstable at learning rate 1e-4 (gradient norms 56 to 152 before clipping). The reading "inconclusive"
stands for that run. This addendum fixes the objective and runs once more. One run, no sweep.

**Changes from the spec above. Everything not listed is unchanged.**

1. **Loss.** Binary cross-entropy on the margin logit(PASS) minus logit(FAIL), with both logits taken before the cap.
   They are computed in float32 from the output head's input (the final hidden state after the last norm) and the
   head's two rows (`last_logits` in `scripts/sft_pilot.py`). Raising both logits no longer lowers the loss, and
   nothing saturates.
2. **Training data.** The whole training pool: every training-split row of at most 6,144 tokens, 990 rows on 184
   issues (450 passing, 540 failing, 190 Gemma's own; 23 longer rows dropped; 1.33 million tokens, longest 6,134).
   File `data/sft-pilot/train_pool.jsonl` (md5 a434e3f8), written by `sft_pilot.py prepare-pool`, order shuffled with
   seed 0. No class weighting. Two epochs in the same order, 495 optimizer steps.
3. **Learning rate** 2e-5, 10 warm-up steps, then linear decay to 0. The user accepted this on the first run's
   gradient norms as a correction, not a search. No other value is tried.
4. **Score.** Primary score unchanged: logit(PASS) minus logit(FAIL) as the model outputs them (after the cap), both
   conditions re-scored in this run. Each score row also stores the two logits before the cap. The same measures on
   the margin before the cap are a named secondary (`analyze --precap`), reported beside the primary. The number of
   distinct score values per condition is reported, since the first run's adapter had 39.
5. **Named secondary slice.** Gemma's own failing patches that it scored 100 as reader (51 in evaluation): false
   acceptance at the development threshold, adapter on minus off, with the issue bootstrap
   (`own_stamped_false_accept_diff`). Too few for a rule; it is read beside the primary as below.
6. **Smoke test time projection.** The smoke test times the longest rows, which run slower per token than the whole
   set. Its projection is multiplied by the first run's ratio of full-run speed to smoke-test speed (training 451 /
   406, scoring 1,865 / 1,407 tokens per second). The other stop rules are unchanged (peak memory 76 GB, finite
   numbers, answer format, elapsed plus projected time within 90% of the cap).
7. **Cap.** 3.5 A100-hours for the whole chain. Expected: smoke test 0.2 h, training 2.66 million tokens at 451
   tokens/s 1.6 h, scoring 4.79 million tokens at 1,865 tokens/s 0.7 h, about 2.6 h in total.

**Readings.** "Improves checking", "no measurable improvement" and "inconclusive" are defined as in the spec, on the
primary score. What each allows:

- Improves checking, and false acceptance on Gemma's own stamped failures falls: run the transfer confirmation below.
- Improves checking, but Gemma's own stamped failures stay accepted (the slice's interval includes 0): report that a
  checker tuned from the writer's weights keeps the writer's blind spot. Supplement material and one sentence.
- No measurable improvement: one limitation sentence. Training stays open.
- Inconclusive: report the numbers. No further training.

**Transfer confirmation, only after "improves checking".** Score the LiveCodeBench programs (Gemma's 124 failing
programs and the other writers' programs, prompts from the LiveCodeBench judging files in the same answer-only
format) with the adapter off and on, about 0.3 A100-hours, separately started with the user's OK. No LiveCodeBench
program was in training. Measure: false acceptance on failing programs at the threshold that keeps 90% of passing
programs, each condition with its own threshold, on minus off, 2,000 resamples of problems. Reading: "transfers" if
the interval is below 0; otherwise "does not transfer". The word "fix" needs "transfers". The label-shuffled control
of the spec still applies before any claim that the gain needs the labels.

**Commands.** On the lab, after the user's OK and with the GPU under 2 GB:

```
cd <workdir>/gemma4-paper-track/sft && \
  OUT=run2 CAP_HOURS=3.5 TRAIN=train_pool.jsonl nohup bash sft_pilot_chain.sh > logs/chain_run2.log 2>&1 &
```

Checked before this addendum, without the GPU, on the 4-layer random Gemma 4 on the Mac: the capped logits from
`last_logits` equal a plain forward pass; the cap applied to the uncapped pair reproduces the capped pair; the loss
equals log(1 + exp(-margin)); gradients reach the adapter and are finite; smoke test, training, scoring and both
analyses run end to end. The first run's analysis is unchanged by the new code (false acceptance 53.0% off, 70.5% on).
