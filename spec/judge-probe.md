# Spec: does Gemma know its patch fails when it says 100? (activation probe and issue likelihood)

Written 2026-11-02, before any activation or likelihood value was computed. Approved by the user the same day (chat:
"let's check activations and such in the lab server"). Background: `notes/fable-aha-fix-2026-11-02.md` (the probe
idea, the ceiling numbers and the measure to use), `notes/lit-judge-fixes-2026-11-02.md` (issue reconstruction and
prior work). Exploratory follow-up to the paper, not part of its frozen plans.

## Question

Gemma 4 31B gives 100 to 61% of its own failing held-out patches, and in all 18 hand-coded cases it names the
defective line and calls it correct. Is the information that the patch fails present in its internal state while it
reads the judging prompt, even though its answer says 100? Two read-outs of the same weights, neither of which asks
Gemma for a verdict:

1. **Activation probe.** A linear classifier on the hidden state of the local 31B (the 4-bit checkpoint that wrote the
   patches) at the last token of the paper's judging prompt, trained only on other writers' patches, tested on
   Gemma's own patches.
2. **Issue likelihood.** How much more likely the real issue text becomes once Gemma has seen the patch:
   mean log-probability per token of the issue given the patch, minus the same given no patch.

## Data

- Patches: the 957 held-out patches scored by all nine original judges (the set of `fresh_judging.load` with the
  nine judges and runs `main-a`, `main-b`): 180 of Gemma's own, 777 by five other writers. Labels: SWE-bench
  resolved, as in the paper.
- Prompts: the exact judging prompts in `data/judge-prompts/heldout_p1.jsonl` (system message plus user message, the
  model's chat template with the generation prompt added, thinking off). Prompts not in the 957 are computed but not
  used in any primary measure.
- "Stamped": own patches the hosted 31B scored 100 (133: 81 passing, 52 failing), the paper's judge. The same with the
  local 31B is reported second.

## Model and features

- `models/gemma-4-31B-it-qat-w4a16-ct` on the lab A100, loaded with HF transformers 5.18.0 and compressed-tensors
  0.17.0, bf16 compute, one forward pass per prompt, no generation. 60 layers, hidden size 5,376.
- Probe features: the hidden state at the last prompt token at every 4th layer (layers 4, 8, ..., 60) plus the final
  normed state, saved as float16.
- Issue likelihood: user message "Here is a patch to the repository <repo>:\n\n<patch>\n\nWrite the GitHub issue that
  this patch fixes." with the issue text as the assistant reply, teacher-forced; and the same with the patch replaced
  by "(no patch)". Issue truncated to its first 1,500 tokens. Score = mean log-probability of the issue tokens with the
  patch minus without. Patch text as in the judging prompt.

## Probe training (fixed now)

- Five folds grouped by issue (`GroupKFold`, issues sorted, no shuffling). For each fold: train on other writers'
  patches of the training issues only; predict all patches of the test issues. Gemma's own patches are never in any
  training set, and no test patch shares an issue with a training patch.
- Classifier: standardize, then L2 logistic regression. Layer and C (0.001, 0.01, 0.1, 1) chosen jointly by an inner
  five-fold issue-grouped cross-validation on the training patches only (mean AUROC). One choice per outer fold.
- Out-of-fold predictions are pooled across the five folds before computing AUROC.

## Measures

Primary (probe):

- P1: AUROC on Gemma's own 180 patches.
- P2: AUROC among the 133 stamped own patches.

Rules, fixed now: **stop** if P1 < 0.70 or P2 < 0.65; **success** if P1 ≥ 0.72 and P2 ≥ 0.68. Between the two:
inconclusive, report as such. For reference: the hosted 31B's own AUROC is 0.62 (P2 0.50 by construction, all ties);
GLM-4.5 0.75 within stamped.

Secondary (all reported, none decides):

- Issue likelihood: the same P1 and P2.
- Probe AUROC on other writers' patches (out of fold), and own minus other, against the 31B's verbal drop.
- Top quarter of Gemma's own patches by the paper's rule (Gemma's score, ties broken by the probe), against the free
  tie-break by fewer model calls (78%).
- Controls: patch length alone (log characters added plus removed, same folds), labels shuffled within issue
  (probe should fall to about 0.5), and the probe with Gemma's own patches added to training (same folds).
- 95% intervals for P1, P2 and differences: 2,000 bootstrap resamples of issues.
- If time allows, the same probe on the 12B (`models/gemma-4-12B-it-qat-w4a16-ct`) as a comparison.

## What each outcome means

- Success: the 31B's internal state separates its own failing patches from passing ones while its answer gives
  them 100. The fix is a read-out, not a prompt: a probe trained on other agents' verified patches.
- Stop: the wrong belief is in the representation as well as in the answer. The paper says so; together with the
  thinking-mode result, reading-based self-review has no easy fix inside these weights.

## Logging

W&B group `judge-probe` (from the Mac, after results come back), changelog entry in `changelog/2026-11-02.md`, outputs
in `scripts/derived/judge_probe_2026-11-02.json`, features kept on the lab server
(`<workdir>/gemma4-paper-track/probe/`).

## Addendum 2026-11-02 (after the held-out result, before any Lite or 12B value): does the probe carry over?

Held-out result: success by the rule above (own 0.741, stamped 0.748; `changelog/2026-11-02.md`). The user approved
the next A100 run in chat. Two parts, fixed now.

### 1. Train once, test on SWE-bench Lite (primary of this addendum)

- Probe: trained once on the held-out issues, other writers' patches only (the 777), layer and C chosen by the same
  issue-grouped five-fold search on those patches. Never refit on Lite.
- Test data: the Lite patches scored by all seven Lite judges (`scripts/third_party_lite.py analyze` set: Gemma 4 31B's
  patches from another team's run, mini-SWE-agent 2.2.1, full weights, thinking on; four leaderboard writers).
  Prompts built with the same `rating_prompt(..., Q_P1)` and system message as the Lite judging. Features from the same
  local 4-bit 31B, same layers and token.
- Primary set: Lite issues not among the held-out issues (no issue seen in training). All Lite issues: secondary.
- "Stamped": Gemma's own Lite patches that the hosted 31B scored 100 in the Lite judging.
- Measures: L1, AUROC on Gemma's own Lite patches; L2, AUROC among stamped own patches. For reference, the hosted
  31B's own AUROC on Lite is 0.637; the best outside judge on Gemma's Lite patches 0.689 (gpt-oss-20b).
- Rule: **carries over** if L2 ≥ 0.65 with its 95% interval (issue bootstrap, 2,000) above 0.5, and L1 ≥ 0.66;
  **does not carry over** if L2 < 0.58 or its interval includes 0.5. Between: inconclusive.
- Secondary: AUROC on the other Lite writers' patches; top quarter of Gemma's own Lite patches (Gemma's score, ties by
  the probe) against Gemma's score alone; the same measures with all Lite issues.

### 2. The same probe on the 12B (comparison named in the spec)

- `models/gemma-4-12B-it-qat-w4a16-ct` (48 layers): hidden state at the same token after layers 4, 8, ..., 44 and the
  final norm; same training and measures as the held-out primary. No pass or stop rule; reported beside the 31B.
  Question: is the information specific to the weights that wrote the patches, or does a smaller sibling hold it too?

## Addendum 2, 2026-11-02 night (before any value below is computed): the score-token baseline

The user asked for overnight work on this line (chat, 2026-11-02: "work overnight with sub agents ... don't update any
paper"); this covers the A100 runs below.

Question: does the probe know more than Gemma's own probabilities at the moment it writes its score? A reviewer's
first baseline is to read the probability of the score instead of the sampled number.

- Pass: teacher-force each recorded answer of the local 31B on the held-out prompts (`fresh_gemma4-31b-local.jsonl`,
  the last parsed answer per patch) up to the score digits (the text before the digits after the last `SCORE:`).
  Capture (a) log P(score = 100) = log P("1" "0" "0" as tokens after the prefix); (b) the next-token probabilities of
  the ten digit tokens at the first score position; (c) the hidden state at the last prefix token (the token before
  the number), same layers as before. Second set: the hosted 31B's recorded answers (`fresh_gemma4-31b.jsonl`),
  teacher-forced through the same local model, because the paper's stamped set is the hosted judge's.
- Measures, on the same 957 patches and folds as the primary:
  - S1: AUROC of log P(100) among the stamped own patches (hosted answers, hosted 100s; and local answers, local
    100s). Compare with the prompt-end probe (0.748 / 0.729).
  - S2: the probe trained at the score position (same procedure), own and stamped AUROC.
- Reading fixed now: if S1 is within 0.03 of the prompt-end probe or above it, the probe adds little beyond Gemma's own
  probabilities, and the fix to report is "read the probability of the score" (cheaper, no training). If S1 is lower
  by more than 0.05 and the interval of the difference excludes 0, the hidden state holds information the spoken
  probability does not. If S2 is at least the prompt-end probe, the information survives to the verdict; if S2 is
  lower by more than 0.05, the written answer loses it.

## Addendum 3, 2026-11-02 night (before any LiveCodeBench activation is computed): a task with no agent

- Same probe, in-domain, on the LiveCodeBench judging set (`data/livecodebench-pilot/judging/programs.jsonl`: Gemma's
  292 programs, DeepSeek-V3's and Claude 3.5 Sonnet's 547 on the same problems), prompts from `lcb_judging.prompt` with
  its own system message (`data/judge-prompts/lcb_p1.jsonl`), the local 31B, the same layers and token.
- Set: programs scored by all six LiveCodeBench judges, as in the paper's LiveCodeBench analysis. Folds grouped by
  problem; probe trained on the other two writers' programs only; same layer and C search.
- Stamped: Gemma's own programs the hosted 31B scored 100 in the LiveCodeBench judging.
- Measures and rule: C1, AUROC on Gemma's own programs (Gemma's own score: 0.662); C2, AUROC among stamped own
  programs. **Holds** if C2 ≥ 0.65 with its interval above 0.5 and C1 ≥ 0.70; **fails** if C2 < 0.58 or its interval
  includes 0.5; between: inconclusive. Caveat fixed now: only 111 of the 547 training programs pass.

## Addendum 4, 2026-11-02 night (before any Qwen activation is computed): the same probe on an outside model

Prior-work check (`notes/lit-probe-prior-work-2026-11-02.md`): hidden-state probes beating spoken confidence are known
(Orgad et al. 2024; Radharapu et al. 2025 for judges), and Ashuach et al. (2026) find a model's own probe often does no
better than a peer model's probe. So the probe matching GLM-4.5 does not show that Gemma holds private knowledge.

- Same held-out prompts, same token (end of the judging prompt, chat template, no thinking: `enable_thinking=False`),
  same layers rule (every 4th layer and the final norm), same training and folds, on Qwen3-32B (bf16, the copy cached
  on the lab server). Qwen3-32B is not a writer here; Qwen3-Coder (a writer) is a related family.
- Measures: Q1, the Qwen probe's AUROC on Gemma's own patches and among the stamped ones; Q2, Gemma's probe minus
  Qwen's probe on the stamped set, with a 95% issue-bootstrap interval.
- Reading fixed now: Gemma's probe higher by at least 0.05 with the interval above 0 → the information is specific to
  Gemma's own state ("Gemma knows but says 100"). Within ±0.03 → it is readable from another capable model's state as
  well; the fix still stands, but the claim becomes "read a model's hidden state instead of its words", not
  introspection. Otherwise: inconclusive.

## Addendum 5, 2026-11-02 night (before any value below is computed): why Lite was inconclusive, and a label-free probe

From the adversarial review (`notes/fable-probe-review-2026-11-02.md`, label-free checks only): Lite's own patches come
from another Gemma setup (full weights, thinking on, mini-SWE-agent 2.2.1) and are much shorter (765 vs 1,900
characters); a "verdict probe" trained on held-out other writers' patches to predict Gemma's own verdict (hosted
score ≥ 90), with no pass/fail labels, scores as well as the labelled probe on held-out (0.775 own, 0.758 stamped).
All on CPU from saved features. "Stamped" on Lite: own patches the hosted 31B scored 100; L2 = 0.635 (addendum 1).

- LI2: in-domain Lite probe. Lite patches only, five issue-grouped folds, trained on other Lite writers' patches,
  same layer and C search; AUROC among stamped own patches on the Lite issues not in the held-out set. D2 = LI2 − L2
  on the same issues, paired issue bootstrap.
- RV2: trained on all Lite other-writer patches, tested on held-out stamped own patches of issues not in Lite.
- PO2: pooled training (held-out and Lite other-writer patches), issue-grouped folds over the union; AUROC among
  stamped own patches on Lite (PO2-lite, unseen issues) and on held-out (PO2-heldout).
- VT2: the verdict probe (trained on held-out other writers to predict hosted score ≥ 90, layer and C chosen by
  inner CV on that target) applied unchanged to Lite; AUROC among stamped own patches on unseen Lite issues.
- Readings fixed now: domain shift if LI2 ≥ 0.68 and the D2 interval is above 0; weak Lite signal if LI2 < 0.62;
  transfer adequate if LI2 is within 0.03 of L2 and both ≥ 0.62. RV2 ≥ 0.68: transfer works in the other direction.
  PO2-lite ≥ 0.65 with its interval above 0.5: pooled training is the recommendation. VT2 ≥ L2 + 0.03: the label-free
  version transfers better and is the one to recommend.

## Addendum 6, 2026-11-02 night (after the held-out score-token result, before any Lite or LiveCodeBench value)

Held-out result (addendum 2, `derived/judge_probe_score_2026-11-02.json`): log P(100) among the stamped own patches
0.756 [0.668, 0.841], the probe 0.748 (difference −0.008 [−0.099, +0.080]). By the reading fixed in addendum 2, the fix
to report is "read the probability of the score". Exploratory, after that result (`derived/judge_probe_logp_extra_2026-11-02.json`): the
own-vs-other ranking gap falls from +0.129 (written score) to +0.033 [−0.031, +0.095]; top quarter 61% → 82%.

Replication on the two other data sets, fixed now:

- Teacher-force the hosted 31B's recorded answers (`lite_gemma4-31b.jsonl`, `lcb_gemma4-31b.jsonl`, last parsed row per
  item) through the local 31B, same code as addendum 2, on the Lite and LiveCodeBench judging prompts. Sets as in the
  paper's analyses (all seven or six judges scored the item).
- Measures per data set: K1, AUROC of log P(100) among stamped own items (hosted score 100); K2, the ranking gap
  (AUROC on other writers' items minus on own items) with log P(100), against the same with the written score.
- Rule: **replicates** on a data set if K1 ≥ 0.65 with its interval above 0.5 and K2 is smaller than the written-score
  gap by at least half; **fails** if K1 < 0.58 or its interval includes 0.5. Otherwise inconclusive.
- Caveat fixed now: the hosted answers came from the hosted model; the probabilities come from the local 4-bit copy.
  On held-out this approximation gave 0.756 (hosted answers) against 0.748 (the local model's own answers).

## Addendum 7, 2026-11-02 night (before any value below is computed): does reading P(100) help every judge?

Reviewer risk (`notes/lit-logprob-judging-2026-11-02.md`): reading the score's probability breaks ties for any coarse
judge. The claim "the self-judging deficit sits in the written number" needs judges that do not judge their own
patches here, measured the same way.

- Non-self judges: Gemma 4 12B and 26B-A4B (their recorded held-out answers, `fresh_gemma4-12b.jsonl`,
  `fresh_gemma4-26b-a4b.jsonl`, teacher-forced through their own weights in HF, same code as addendum 2), and
  Qwen3-32B (bf16; new answers with vLLM at temperature 0, thinking off, the paper's prompt and 3,000-token limit via
  `scripts/local_judging.py run`, then teacher-forced).
- Measure: gain = AUROC with log P(100) minus AUROC with the written score, on the 31B's own 180 patches and on the
  other writers' 777. The 31B's gain on its own patches: +0.117 (local answers; +0.133 hosted).
- Rule: **the repair is specific to self-judging** if the 31B's gain on its own patches exceeds each non-self judge's
  gain on the same 180 patches by at least 0.05, with the paired interval above 0, for at least two of the three
  judges; **it is general tie-breaking** if two or more non-self judges gain within 0.03 of the 31B. Otherwise mixed.
  Also report each judge's share of ties at its most common score on these patches.

## Addendum 8, 2026-11-02 night (before any value below is computed): sampling baseline

From the review of the probability result (`notes/fable-logprob-review-2026-11-02.md`): the gain from log P(100) is
mostly across issues (difficulty) and tracks how many 100s a writer receives; it may be any way of un-rounding the score.

- Local 31B served with vLLM (the paper's checkpoint), the paper's prompt, 8 samples per patch at temperature 1.0
  (top_p 1.0), 3,000-token limit, thinking off; the mean parsed score over the samples that parsed. All 957 held-out
  patches.
- Measure: AUROC of the mean sampled score among the 133 stamped own patches (hosted 100s), against log P(100)
  (0.756, hosted answers teacher-forced), paired issue bootstrap.
- Rule: within 0.03 of 0.756 → any un-rounding works (the probability is a cheap way to get it); lower by more than
  0.05 with the interval excluding 0 → the probability carries more than resampling. Otherwise inconclusive.

## Addendum 9, 2026-11-02 night (before any value below is computed): the hesitant 100 on SWE-bench Lite

On the held-out issues (exploratory, cut chosen after looking): among the hosted 31B's 100s on its own patches, those
with P(100) below 0.999 passed 25% of the time (9 of 36), those at or above 74% (of 97). The cut 0.999 is now fixed.

- Test set: SWE-bench Lite, hosted answers teacher-forced through the local 31B (`score_lite`, addendum 6), stamped own
  patches (the hosted 31B's 100s on Gemma's own patches, all 229, and also the subset on issues not in the held-out set).
  Second test: LiveCodeBench (`score_lcb`), same cut.
- Measure: pass rate at or above 0.999 minus pass rate below 0.999; issue bootstrap interval.
- Rule: **replicates** if the difference is at least 0.20 with the interval above 0 on Lite; **fails** if the interval
  includes 0. Also report the same on other writers' 100s, and the share of stamped own patches below the cut.

## Addendum 10, 2026-11-02 night (before any value below is computed): Qwen3-32B read at its own top score

Addendum 7's Qwen3-32B result is not like-for-like. Qwen wrote 100 on 1 of the 31B's 180 own patches; its most common
score there is 95 (109 patches, 61%). Reading P(100) for Qwen reads a score it does not use, so its small gain (+0.029)
may say nothing about tie-breaking. The 31B's 100 and Qwen's 95 are each judge's top tie.

- Measure: teacher-force Qwen's recorded answer up to its score and read log P("95") (the digit tokens "9","5"), same
  code as addendum 2 with the target string changed (`probe_extract.py score --target 95`). Gain = AUROC with log
  P(95) minus AUROC with the written score, on the 180 own patches, paired issue bootstrap; also AUROC of log P(95)
  among Qwen's 95s on own patches.
- Rule: addendum 7's rule is applied again with this Qwen gain in place of the P(100) gain. If the two readings
  disagree, the paper reports addendum 7's outcome as not settled.
