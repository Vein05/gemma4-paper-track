# Rubber Stamp: Gemma 4 Scores Its Own Failing Patches as Sure to Pass

**Subtitle.** Asked to check SWE-bench patches without knowing who wrote them, Gemma 4 31B gives most of its own
failing patches the top score, which outside judges do not. A second judge lets an agent built on Gemma pick out the
patches it can submit without review.

Status: draft of 2026-10-06, written from `changelog/2026-10-05.md` and `changelog/2026-10-06.md`. Every number
traces to a file in `scripts/derived/`. Items to finish before submission are listed at the end.

## Abstract

A coding agent has to decide when its patch is done: submit it, try again, or ask a person. That decision is only as
good as the agent's check of its own work. We tested how well Gemma 4 31B checks its own patches. Nine open models
scored the chance that each patch passes the hidden tests of its SWE-bench Verified issue, without being told who
wrote it.

Gemma gives a score of 100 to about 60% of its own failing patches, against 20% to 35% of other writers' failing
patches. This holds on two issue sets and when its patches come from the same agent harness as everyone else's.
Outside judges scoring the same patches do not follow Gemma. Gemma also ranks its own patches less accurately than
they do, though by half as much as our first estimate. Five other models show no such gap.

The cost to an agent is concrete. If it submits without review only the quarter of its patches that its check trusts
most, 61% of them pass when Gemma checks itself. Averaging Gemma's score with that of a 9-billion-parameter open model
raises this to 76%, and GLM-4.5 as the check raises it to 84%.

## 1. Introduction

Coding agents end a task by deciding that their patch is done. Many agents and agent papers ask the same model to
judge its own work, for example to pick among attempts or to decide when to stop. That works only if the model judges
its own patches as well as it judges anyone else's.

We measured this for Gemma 4 31B, the model of this competition. Each judge saw an issue and one patch, wrote a short
explanation, and gave a 0 to 100 score for the chance that the patch passes the hidden tests. The prompt never named
the author. To separate a judge's view of its own work from how hard the patches are, we compare it with outside
judges, models from other families scoring the same patches.

Our first look used public Gemma patches from four agent harnesses, while every other writer's patches came from one
harness, mini-SWE-agent. To remove that difference, we ran Gemma 4 31B in mini-SWE-agent ourselves, on the same 50
issues and on 200 held-out issues, under a plan written before the runs. The story has four parts:

1. Gemma rubber-stamps its own failing patches, in every patch set we tested (Section 3.1).
2. It also ranks its own patches less accurately than outside judges do, but half of the first estimate came from the
   harness difference (Section 3.2).
3. Five other models judge their own patches as well as outside judges do (Section 3.3).
4. A second judge removes much of the problem for an agent deciding what to submit (Section 3.5).

Section 4 turns these steps into an audit any team can run on its own agent's self-check.

## 2. Setup

**Patch sets.** All issues come from SWE-bench Verified. Other writers' patches are public mini-SWE-agent submissions
by GLM-4.5, gpt-oss-120b, Kimi-K2, Llama-4-Maverick, Qwen3-Coder and, on the Mini issues, Devstral
([SWE-bench experiments](https://github.com/SWE-bench/experiments)), with official labels. Test files were removed
from every patch, and patches over 30,000 characters were dropped.

| Patch set | Issues | Gemma's patches | Patches scored by all nine judges (Gemma's / others') |
|---|---|---|---|
| Mini issues, mixed harness | 50 (django, sphinx) | public runs in four harnesses | 150 / 183 |
| Mini issues, matched harness | the same 50 | ours, mini-SWE-agent | 41 / 183 |
| Held-out issues | 193, from 11 repositories | ours, mini-SWE-agent | 180 / 777 |

The Mini issues are SWE-bench Verified Mini
([dataset](https://huggingface.co/datasets/MariusHobbhahn/swe-bench-verified-mini)). Their mixed-harness Gemma patches
come from public third-party runs in SWE-agent, openclaw, opencode and zeroclaw
([AlphaDiana datasets](https://huggingface.co/n-pelleriti)). The held-out issues are a fixed random sample of 200
SWE-bench Verified issues outside the Mini issues. For our own runs, the 4-bit competition checkpoint of Gemma 4 31B
made one attempt per issue in mini-SWE-agent v1.7.0, with its default settings and temperature 0. We graded the
patches with SWE-bench's grading code and kept an issue only if its reference patch passes in our environment. This
dropped 7 of the 200 held-out issues. Gemma solved 98 of the 193 kept issues.

**Judges.** Nine models judged every patch: Gemma 4 31B, gpt-oss-20b, Qwen3.5-9B, GLM-4.7-Flash, and the five writers
above other than Devstral. Calls went through OpenRouter at temperature 0 with reasoning switched off, except gpt-oss,
which always reasons and ran at low effort. The prompt holds the issue text and the patch, and the answer ends with a
score. An answer without a score was asked once more with a larger output limit, a step we call a re-ask. Analyses use
the patches that all nine judges scored.

**Measures.**
- AUROC: the chance that a judge scores a random passing patch above a random failing one (ties count half).
- Self-judging gap: how much a model's AUROC drops from other writers' patches to its own, minus the same drop for
  outside judges.
- Leniency: a judge's score on a patch minus the outside judges' mean score on that patch, compared between a model's
  own failing patches and other writers' failing patches.
- Rubber-stamp rate: the share of a judge's own failing patches that it scores 100.

Intervals are 95% intervals from 2,000 bootstrap resamples of issues.

**Plans.** Every test had a written plan with its reading rule before its data was computed (all in `spec/`). Two
changes came after the plan for our own patch sets. Both came before any of their results were read: we added the leniency
measure, and we raised the re-ask limit from 3,000 to 8,000 tokens because many answers ran out before the score.
Analyses chosen after we saw a result are marked exploratory.

## 3. Results

![Self-judging gap on three patch sets and Gemma 4 31B's scores on failing patches](figures/fig-results.png)

**Figure 1.** (a) Gemma 4 31B's self-judging gap on each patch set, with 95% intervals. The open circle leaves out
every held-out patch that needed a re-ask (exploratory). The diamond is the pooled gap of five other models judging
their own patches. (b) Gemma's scores on failing patches, its own and other writers', per patch set.

### 3.1 Gemma rubber-stamps its own failing patches

| Patch set | Own failing patches scored 100 | Other writers' failing patches scored 100 | Leniency on failing patches [95%] |
|---|---|---|---|
| Mini issues, mixed harness | 61% (49 of 80) | 20% (of 103) | +20.9 [11.5, 30.2] |
| Mini issues, matched harness | 57% (12 of 21) | 20% (of 103) | +11.7 [−1.4, 24.2] |
| Held-out issues | 61% (52 of 85) | 35% (of 393) | +16.6 [10.3, 23.1] |

Gemma's rubber-stamp rate stays near 60% whatever the issues or the harness. Some of this comes from the patches
themselves, since some outside judges also give Gemma's failing patches a perfect score more often. Leniency
removes that part by comparing judges on the same patch. On the held-out issues, Gemma scores its own failing patches
16.6 points above the outside judges, more than it does for other writers' failing patches. On passing patches there
is no such excess (+3.4 [−2.0, 8.0]), so the extra trust goes to exactly the patches Gemma should reject.

This result does not depend on the larger re-ask limit. Leaving out every patch that needed a re-ask, the leniency on
the held-out issues is +11.1 [3.8, 18.2] (exploratory). The matched-harness Mini set has only 21 failing patches, so
its interval is wide.

### 3.2 The ranking gap is real but smaller than first measured

| Patch set | Gemma's AUROC, own patches | Gemma's AUROC, other writers' | Self-judging gap [95%] |
|---|---|---|---|
| Mini issues, mixed harness | 0.636 | 0.833 | +0.135 [0.060, 0.210] |
| Mini issues, matched harness | 0.695 | 0.833 | +0.070 [−0.024, 0.168] |
| Held-out issues | 0.622 | 0.751 | +0.074 [0.022, 0.126] |

Rubber-stamping should also hurt Gemma's ranking of its own patches, since ties at 100 hide which ones fail. The gap
measures this. On the same 50 issues, switching Gemma's patches to the matched harness halved it, while the outside
judges' drop on Gemma's patches stayed about the same. So about half of the first gap went with the harness that wrote the
patches.

On the held-out issues, the gap meets the reading rule we fixed in advance, with little margin. It also depends on
the larger re-ask limit: leaving out every patch that needed a re-ask gives +0.030 [−0.024, 0.083] (exploratory). We
therefore treat the ranking gap as suggestive and the leniency in Section 3.1 as the firm result.

### 3.3 Only Gemma shows the gap

On the Mini issues, five of the other writers judged their own mini-SWE-agent patches, so the harness is matched for
them by construction. None shows a gap.

| Model judging its own patches | AUROC, own patches | AUROC, other families' patches | Self-judging gap [95%] |
|---|---|---|---|
| Qwen3-Coder | 0.691 | 0.786 | −0.032 [−0.241, 0.189] |
| gpt-oss-120b | 0.860 | 0.701 | −0.046 [−0.133, 0.049] |
| GLM-4.5 | 0.757 | 0.752 | −0.047 [−0.174, 0.116] |
| Kimi-K2 | 0.881 | 0.805 | −0.036 [−0.113, 0.036] |
| Llama-4-Maverick | 0.786 | 0.657 | −0.019 [−0.133, 0.101] |

Pooled over the five, the gap is −0.036 [−0.089, 0.016]. Leniency is less clear for them, because each wrote only 14
to 24 failing patches. Their point estimates range from −5.4 to +17.5 points, without intervals. Llama-4-Maverick's is
close to Gemma's, but Maverick also scores other writers' failing patches 95 or above more often than its own.

### 3.4 What the deficit is not

We checked four simple explanations on the mixed-harness patches.

- **Patch size.** Gemma's patches are smaller than the other writers', but among failing patches of similar size its
  extra leniency on its own stays at 24.1 points [12.7, 39.9].
- **Missing reasoning.** Switching Gemma's thinking on leaves its AUROC on its own patches unchanged (0.638 against
  0.636).
- **Issues it cannot solve.** It scores two thirds of its own failing patches at 95 or above, whether or not one of
  its attempts solved the issue.
- **Choosing among attempts.** Given two of its own patches for the same issue, Gemma picks the passing one about as
  often as outside judges do. It falls behind them only when the two patches belong to different issues.

### 3.5 What a second judge buys an agent

![AUROC of each check on Gemma 4 31B's own patches, minus Gemma's AUROC](figures/fig-checks.png)

**Figure 2.** Each check's AUROC on Gemma's own patches minus Gemma's AUROC on the same patches. Lines are 95%
intervals on the 180 held-out patches; hollow points are the two Mini patch sets. "Gemma + X" averages the two
judges' ranks of each patch. Cost is the OpenRouter price per 1,000 patches in US dollars.

Consider an agent that submits some of its patches without review and sends the rest to a person. The table shows
what share of the submitted patches pass, on the held-out issues, if the agent submits the quarter or the half of
its patches that its check ranks highest. Without any check, 53% pass.

| Check | Submit top quarter: share passing [95% interval of gain over Gemma, points] | Submit top half: share passing [same] |
|---|---|---|
| Gemma's own score | 61% | 61% |
| Gemma + Qwen3.5-9B | 76% [+6.7, +23.3] | 68% [+1.5, +12.0] |
| Kimi-K2 | 77% [+9.6, +22.5] | 72% [+5.9, +17.6] |
| GLM-4.5 | 84% [+12.7, +32.0] | 74% [+6.8, +18.3] |

Gemma's own score cannot make the agent more selective. It gives 100 to 74% of its patches, so the top quarter and
the top half are random draws from that tied group, and 61% of them pass either way. A second judge breaks the tie.
The best results come from GLM-4.5 and Kimi-K2. On its own, Qwen3.5-9B's gain over Gemma is within the margin of error.
Averaged with Gemma's ranks, at two cheap calls per patch, it is a clear gain.

These checks were chosen after we had seen their AUROCs, so this comparison is exploratory. We cannot tell whether the
outside judges help because they come from another family or because they judge better in general. Gemma's own
signals helped less: on the mixed-harness patches, adding agreement between its attempts raised its AUROC by 0.074
[−0.014, 0.160], short of our planned bar.

## 4. Auditing an agent's self-check

The method carries over to any model and benchmark. A team that wants to trust its agent's own verdicts can run three
steps on patches with known outcomes:

1. **Compare with outside judges on the same patches.** A model may rank its own patches poorly only because they are
   hard. Subtracting the outside judges' drop on the same patches removes that.
2. **Match the harness.** Patches from different harnesses differ in more than their author. In our data, half of
   the first gap came from this difference.
3. **Measure leniency on failing patches, patch by patch.** Ranking measures mix leniency with issue difficulty and
   ties. Comparing judges on the same patch isolates the part a team can act on: patches the model passes that it
   should reject.

Applied to six models, the first two steps flagged only Gemma 4 31B. The third step needs more failing patches per
model than the other five wrote here. For an agent built on Gemma, the practical advice is to
let a second model decide which patches go out without review. This matters for submitting, opening pull requests and
handing work to people. It does not matter for choosing among several attempts at one issue, where Gemma's ranking is
as good as the outside judges'. In this competition's scorer, which runs one Gemma model on one task at a time, there
is no second judge to call.

## 5. Related work

Judges that favor their own outputs have been studied mostly on text and short programs. Panickssery et al. (2024)
link the strength of this self-preference to how well a model recognizes its own summaries. Wataoka et al. (2024)
relate it to the perplexity of the preferred response. Roytburg et al. (2026) compare a judge's own failing answers
with other models' failing answers to the same question, and much of the measured self-preference goes away. Our
leniency measure also compares judges on the same patch. Chen et al. (2025) find that stronger judges more often
prefer their own wrong answer to a correct one.

Two studies are closest to ours. Pombal et al. (2026) check programs from twelve models against unit-test rubrics and
find that judges favor their own outputs even with objective rubrics. On LiveCodeBench, Gemma 3 12B and 27B do not:
their ratios are 0.97 and 1.03, where 1 means no self-preference. Khullar et al. (2026) find that a model rates a
SWE-bench patch as more correct when it is framed as the model's own earlier answer. When the patch is shown in a user
turn, their ratings separate passing from failing patches with AUROC 0.99, for one unnamed model and with no comparison
to other writers' patches.

Our setting differs in three ways. The patches come from full agent runs, the judge sees no authorship or framing cue,
and we measure ranking accuracy against hidden tests with outside judges as the control. In this setting five of six
models judge their own patches as well as outside judges do, while Gemma 4 does not, unlike the Gemma 3 models Pombal
et al. tested.

## 6. Limitations

- **What transfers.** The audit method applies to any model and benchmark. The finding is about Gemma 4 31B on
  SWE-bench Verified. We do not know which part of its training causes it, or whether Gemma recognizes its own patches
  or shares the mistakes in them.
- **Writer and judge precision.** Our matched-harness Gemma patches come from the 4-bit competition checkpoint, while Gemma as
  judge is the hosted full-precision model. In an earlier check on 173 other patches, the two gave the same one-word
  answer in 331 of 344 calls.
- **Labels from two sources.** Other writers' labels are SWE-bench's official ones, while we graded our Gemma patches
  ourselves. On 30 issues, 26 other-writer patches got their official label in our environment; the misses came from
  rebuilt images and environment faults.
- **Changes after the plan.** The leniency measure and the larger re-ask limit came after the plan was fixed. The
  held-out ranking gap depends on the second.
- **Size.** One attempt per issue in our own runs, and only 41 matched-harness patches on the Mini issues.

## 7. Reproducibility and cost

All data are public, and no competition data was sent to an outside service. The repository holds the code, prompts,
plans, every judge answer, Gemma's matched-harness patches and trajectories, and their labels; its README lists the script behind
each section and the cost of each run. Our 250 Gemma agent runs took 49 agent-hours on one NVIDIA L40S of a
university cluster. All judging cost $12.36 at OpenRouter prices.

## Before submission (not part of the writeup)

1. Grade the second `django__django-11848` patch (needs a Magnolia job, see `changelog/2026-10-06.md`), run
   `scripts/mini50_analysis.py` again without `--drop`, and update Sections 3.1 and 3.2 and Figure 1.
2. Calibrated scorer on the final version; compare drafts only within one scorer run.
3. Word count (3,000 at most), AI-use disclosure, public repository link.
4. Check the related-work paragraph against the changed framing (rubber-stamping first, gap second).
