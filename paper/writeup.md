# Rubber Stamp: Gemma 4 Checks Other Agents' Patches Well and Its Own Poorly

**Subtitle.** Nine open models judged 388 SWE-bench patches in a fresh context. Only Gemma 4 31B judges its own
patches worse than outside judges do: its scores on its own patches pile up at the top of the scale.

Status: draft of 2026-10-05, written from the results in `changelog/2026-10-05.md`. Every number traces to a file
in `scripts/derived/`. Items to finish before submission are listed at the end.

## Abstract

An agent that checks its own patch decides when to stop, retry or ask a human. We asked nine open models to rate
the chance that a patch passes the hidden tests of its SWE-bench issue. The patches came from Gemma 4 31B agents and
from six other models, all on the same 50 issues.

Gemma 4 ranks other writers' patches well (AUROC 0.83) but its own poorly (0.64), below a 9-billion-parameter
outside judge (0.76). Five other models show no such gap on their own patches. The effect survives a control for
patch size, and switching on Gemma's thinking does not change its accuracy on its own patches.

Gemma gives exactly 100 to 110 of its 150 own patches, 49 of which fail. It ranks two of its own patches for the
same issue about as well as outside judges do, but its scores barely separate one issue from another. Its high scores
on failing patches do not depend on whether it ever solves the issue. Adding agreement between Gemma's own attempts to its score closes 61% of the gap to outside judges,
but the interval on 50 issues includes zero. For agents built on Gemma, a second model is the better check of a
finished patch, while choosing among Gemma's own attempts is not affected.

## 1. Introduction

Coding agents end a task by deciding that their patch is done. Many agents and agent papers ask the same model to
judge its own work, for example to pick among several attempts or to decide when to stop. That works only if the
model judges its own patches as well as it judges anyone else's.

We measured this directly for Gemma 4 31B, the model of this competition, and for five other open models. Each
judge saw an issue and one patch, wrote a short explanation, and gave a 0 to 100 score for the chance that the
patch passes the hidden tests. The judge was never told who wrote the patch. We call this a pointwise rating. We
compare each judge's accuracy on its own patches with its accuracy on other writers' patches, and subtract the same
difference for outside judges, judges from a different model family than the writer.

Three findings:

1. **The gap is specific to Gemma 4.** Gemma's AUROC drops by 0.20 from other writers' patches to its own, against a
   drop of 0.06 for outside judges on the same patches. None of five other models that wrote patches shows a gap.
2. **The gap is about issues, not attempts.** On two of its own patches for the same issue, Gemma picks the passing
   one about as often as outside judges do. On patches for different issues it falls behind them, because it gives
   nearly all of its own patches the top score.
3. **It is not fixed by thinking, and only partly by Gemma's own signals.** Thinking leaves the self-check unchanged.
   Combining Gemma's score with how much its attempts agree recovers part of the gap, short of statistical support.

## 2. Setup

**Issues and patches.** We used the 50 issues of SWE-bench Verified Mini, 25 from django and 25 from sphinx
([dataset](https://huggingface.co/datasets/MariusHobbhahn/swe-bench-verified-mini)). Gemma 4 31B patches come from
public third-party runs of Gemma agents in four harnesses: SWE-agent, openclaw, opencode and zeroclaw, plus one
patch from a single-call run ([AlphaDiana datasets](https://huggingface.co/n-pelleriti)). Identical patches from
different runs count once. Patches from six other writers (gpt-oss-120b, GLM-4.5,
Qwen3-Coder, Kimi-K2, Llama-4-Maverick and Devstral) come from public mini-SWE-agent submissions on the same issues
([SWE-bench experiments](https://github.com/SWE-bench/experiments)). Labels are the official SWE-bench evaluation
results. Test files were removed from patches, and patches over 30,000 characters were dropped. This left 388
usable patches: 174 by Gemma and 214 by the other writers.

**Judges.** Nine models judged every patch: Gemma 4 31B, gpt-oss-20b, Qwen3.5-9B, GLM-4.7-flash, and the five
writers above other than Devstral. All calls went through OpenRouter at temperature 0 with the model's internal
reasoning switched off, except gpt-oss, which always reasons and ran at low effort. The prompt contains the issue
text and the patch, never the author. 333 patches received a parsed score from all nine judges; the analyses use
those.

**Measures.** AUROC is the probability that a judge scores a randomly chosen passing patch above a randomly chosen
failing one, with ties counted as half. The self-judging gap of a model is its AUROC on other writers' patches
minus its AUROC on its own, minus the same drop for outside judges. Leniency is a judge's score minus the mean
score of outside judges on the same patch, reported on failing patches. All intervals are 95% intervals from 2,000
bootstrap resamples of issues.

**Pre-registration.** Each test had a written plan with its reading rule before its data was computed
(`spec/self-judging-replication.md`, `spec/own-patch-mechanism.md`, `spec/self-check-fix.md`). The Gemma result was
found first in an exploratory look; the five-model replication was planned after it. One plan contained a sign
error in its reading rule, recorded in the plan before results were reported.

## 3. Results

### 3.1 Only Gemma judges its own patches worse

| Model judging its own patches | AUROC, own patches | AUROC, other families' patches | Self-judging gap [95%] |
|---|---|---|---|
| Gemma 4 31B | 0.636 | 0.833 | +0.135 [0.060, 0.210] |
| Qwen3-Coder | 0.691 | 0.786 | −0.032 [−0.241, 0.189] |
| gpt-oss-120b | 0.860 | 0.701 | −0.046 [−0.133, 0.049] |
| GLM-4.5 | 0.757 | 0.752 | −0.047 [−0.174, 0.116] |
| Kimi-K2 | 0.881 | 0.805 | −0.036 [−0.113, 0.036] |
| Llama-4-Maverick | 0.786 | 0.657 | −0.019 [−0.133, 0.101] |

Pooled over the five planned replications the gap is −0.036 [−0.089, 0.016]: the effect does not generalize to these
models. Sources: `derived/self_judging_replication_2026-10-05.json`, `derived/own_patch_mechanism_2026-10-05.json`.

Gemma is also lenient on its own failing patches. Relative to outside judges it scores them 23.0 points higher
[12.7, 33.6] than the other writers' failing patches on the same issues. On passing patches the difference is −2.8
[−13.3, 8.1]. Smaller models judging patches from their own family show no such leniency
(`derived/self_preference_control_2026-10-05.json`).

### 3.2 What the gap is not

**Patch size.** Gemma's patches are much smaller than the other writers' (7.7 against 72.7 added lines on average).
Comparing single-file failing patches of similar size, Gemma's leniency on its own patches stays 24.1 points
[12.7, 39.9] above its leniency on other writers' patches. On small failing patches by other writers, Gemma is
stricter than outside judges; on its own, it is more lenient.

**Missing reasoning.** We rated all 388 patches again with Gemma's thinking switched on.

| Gemma 4 31B | Reasoning off | Thinking on |
|---|---|---|
| AUROC, own patches | 0.636 | 0.638 |
| AUROC, other writers' patches | 0.833 | 0.795 |
| Own failing patches scored 95 or above | 65% | 64% |
| Other writers' failing patches scored 95 or above | 22% | 35% |
| Self-judging gap [95%] | +0.135 [0.060, 0.210] | +0.097 [0.010, 0.192] |

Thinking does not improve the check on Gemma's own patches. The gap shrinks only because thinking makes Gemma less
accurate on other writers' patches (`derived/own_patch_mechanism_think_2026-10-05.json`).

### 3.3 Where the gap is: across issues

We split all pass/fail pairs of Gemma's own patches into same-issue pairs and different-issue pairs, and computed
pair accuracy (ties count half).

| Pairs of Gemma's own patches | Number | Gemma | Outside judges (mean) | Gemma minus outside [95%] |
|---|---|---|---|---|
| Same issue | 47 | 0.628 | 0.646 | −0.019 [−0.243, 0.148] |
| Different issues | 5,553 | 0.636 | 0.706 | −0.070 [−0.138, −0.006] |

Gemma falls behind outside judges only when the two patches belong to different issues. With 47 same-issue pairs we
cannot claim it matches them within an issue; we detect no deficit there.

The reason is rubber-stamping: Gemma gives exactly 100 to 110 of its 150 own patches, and 49 of those fail. We
call the share of a judge's own failing patches that get the top score its rubber-stamp rate; for Gemma it is 61%
(49 of 80). Its scores
therefore carry little information about which issue a patch belongs to. Breaking those ties perfectly would raise
its AUROC from 0.64 to 0.91.

The high scores do not come from issues that are too hard for Gemma. On issues that one of its attempts solved, it
scores 66% of its failing patches at 95 or above. On issues no attempt solved, the share is 67%. On other writers'
failing patches for those unsolved issues, Gemma is slightly stricter than outside judges (−5.8 points). The account
"a model cannot verify what it cannot solve" does not fit.

We cannot yet tell whether Gemma recognizes its own patches or responds to some property they share. It is not more
lenient toward other writers' patches that resemble its own wrong fix (+5.6 [−5.5, 17.4]). Most of those patches,
however, share almost no changed lines with Gemma's, so this test is weak.

### 3.4 Who should check Gemma's patches

| Judge of Gemma's own patches | AUROC [95%] | Gemma minus this judge [95%] |
|---|---|---|
| Gemma 4 31B | 0.636 [0.556, 0.710] | |
| Qwen3.5-9B | 0.762 [0.662, 0.845] | −0.127 [−0.227, −0.025] |
| Kimi-K2 | 0.764 [0.674, 0.845] | −0.129 [−0.210, −0.046] |
| Qwen3-Coder | 0.734 [0.647, 0.815] | −0.098 [−0.179, −0.018] |
| Llama-4-Maverick | 0.603 [0.509, 0.699] | +0.032 [−0.047, 0.111] |

The other four judges (gpt-oss-20b, gpt-oss-120b, GLM-4.5, GLM-4.7-flash) score 0.67 to 0.72; their differences
from Gemma have intervals that include zero. Used as a filter that accepts a
patch at a score of 95 or above, Gemma accepts 89% of its passing patches, and 54% of what it accepts passes. With
Qwen3.5-9B as the filter the two numbers are 93% and 63%.

### 3.5 A partial fix from Gemma's own signals

A fix must add information about which issues are hard; shifting all scores up or down cannot change AUROC. We tested
signals that need no training and no second model, fixed in advance, on 172 own patches with both Gemma scores.

| Signal | AUROC | Change from Gemma's score [95%] |
|---|---|---|
| Gemma's score (reasoning off) | 0.646 | |
| Mean of Gemma's scores with reasoning off and thinking on | 0.677 | +0.031 [−0.005, 0.069] |
| Agreement between Gemma's attempts at the issue | 0.665 | +0.019 [−0.119, 0.146] |
| Gemma's score plus attempt agreement (planned test) | 0.720 | +0.074 [−0.014, 0.160] |
| Gemma's score relative to its other attempts at the issue | 0.533 | −0.113 [−0.197, −0.025] |

The planned combination closes 61% of the distance to the outside judges' mean (0.638 to 0.718 against 0.770 on the
same patches), but its interval includes zero, so our rule counts it as not shown. Scoring a patch only relative to
Gemma's other attempts removes the issue-level information and loses accuracy, as the across-issue account predicts.
Source: `derived/self_check_fix_2026-10-05.json`.

Two signals found after the planned test, and so exploratory, point the same way. Smaller own patches pass more often,
and Gemma's score plus patch size, or its two scores used as tie-breakers, raise AUROC to about 0.73. Both need
confirming on new Gemma patches, since patch size may stand in for the harness that wrote the patch.

## 4. What this means for agents built on Gemma 4

The self-check matters for some decisions more than others. Choosing among several attempts at one issue uses only
the ranking within that issue, where we found no deficit. Other decisions need the across-issue judgment: whether a
patch is good enough to submit, to open as a pull request, or to hand to a person. There, Gemma scores two thirds of
its failing patches at 95 or above.

In this competition, an empty patch scores the same as a wrong one, and the scorer runs tasks one at a time on one
Gemma model. Abstaining therefore gains nothing, and several full attempts per task do not fit the time budget. The
finding matters most outside the leaderboard: for an engineer deciding which Gemma patches to trust, a small second
model is the better check. Attempt agreement would need several attempts per issue, which costs agent time.

## 5. Related work

Judges that favor their own outputs have been studied mostly on text and short programs. Panickssery et al. (2024)
link the strength of this self-preference to how well a model recognizes its own summaries. Wataoka et al. (2024)
relate it to the perplexity of the preferred response. Roytburg et al. (2026) compare a judge's own failing answers with other models' failing answers to the same
question, and much of the measured self-preference goes away. Our leniency measure uses the same matching on issues. Chen et al. (2025) find that stronger judges
more often prefer their own wrong answer to a correct one.

Two studies are closest to ours. Pombal et al. (2026) check programs from twelve models against unit-test rubrics and
find that judges favor their own outputs even with objective rubrics. On LiveCodeBench, Gemma 3 12B and 27B do not:
their ratios are 0.97 and 1.03, where 1 means no self-preference. Khullar et al. (2026) find that a model rates a SWE-bench
patch as more correct when it is framed as the model's own earlier answer. When the patch is shown in a user turn,
their ratings separate passing from failing patches with AUROC 0.99, for one unnamed model and with no comparison to
other writers' patches.

Our setting differs in three ways. The patches come from full agent runs, the judge sees no authorship or framing cue,
and we measure ranking accuracy against hidden tests with outside judges as the control. In this setting five of six
models judge their own patches as well as outside judges do, while Gemma 4 does not, unlike the Gemma 3 models Pombal
et al. tested.

## 6. Limitations

- **One model shows the effect.** The finding is about Gemma 4 31B. We do not know which part of its training
  causes it.
- **Third-party runs.** Gemma's patches come from public runs whose settings we did not control. They come from four
  harnesses, while all other writers used mini-SWE-agent. The gap appears in each of Gemma's four harnesses, but
  harness and model are not fully separated.
- **Small, narrow sample.** 50 issues from two repositories; 150 Gemma patches rated by all judges.
- **Selection after discovery.** The Gemma result was found in an exploratory look and then tested on new models.
  A replication on new Gemma patches would likely show a smaller gap.
- **Precision.** Results use the hosted full-precision Gemma 4 31B, not the 4-bit checkpoint of the competition. In an
  earlier one-word check on 173 other patches, the 4-bit checkpoint gave the same answer as the hosted model in 331
  of 344 calls.
- **Labels.** Hidden-test outcomes have known noise in SWE-bench.

## 7. Reproducibility and cost

All data are public. Code, prompts, plans and per-call outputs are in this repository: rating runs
`scripts/self_preference.py`, analyses `scripts/self_judging_replication.py`, `scripts/own_patch_mechanism.py` and
`scripts/self_check_fix.py`. No competition data was sent to any outside service.

API cost, as reported by OpenRouter per call (sums of the `cost` field in `scripts/derived/`):

| Run | Calls | Cost (USD) |
|---|---|---|
| Four judges on Gemma's own attempts (ratings reused here) | 3,244 | 0.53 |
| Nine judges on 388 patches, reasoning off | 3,292 | 2.66 |
| Gemma 4 31B with thinking on, 388 patches | 401 | 0.51 |
| Analyses in Sections 3.2 to 3.5 | 0 | 0.00 |
| **This study** | **6,937** | **3.70** |

gpt-oss-120b calls were reported at zero cost by their provider. Earlier experiments of this project on other
questions cost 9.27; the project total is 12.97. No paid GPU time was used for this study.

## Before submission (not part of the writeup)

1. Done 2026-10-05: §5 rewritten from `notes/reading-khullar-chae-2026-10-05.md` and
   `notes/reading-self-preference-2026-10-05.md`; Singh et al. dropped.
2. Add `citations.md` rows for SWE-bench Verified Mini, the AlphaDiana datasets, SWE-bench, mini-SWE-agent and
   SWE-bench experiments, then build `references.bib`.
3. Decide whether to test the issue-difficulty signal (one Gemma call per issue, about $0.05) before writing
   Section 3.5 in final form.
4. Calibrated scorer: run on this draft on 2026-10-05 (4.02 ± 0.19, `scorer/runs/2026-10-05-writeup/`); run it again on
   the final version.
5. Word count, figures (`../figures/` pipeline), and a public notebook or repository link.
