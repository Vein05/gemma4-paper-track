# Spec: two checks on existing data before the bug-token log-probability test

Written 2026-11-02, before either check was computed. The user's OK: 2026-11-02 ("run these"). No GPU, no API
credit. Exploratory: both checks decide whether the bug-token test in `spec/own-patch-likelihood.md` is worth its
A100 time; neither goes into the Kaggle paper. Background: `notes/idea-own-code-surprise-2026-10-28.md` (the idea, and
result 3: same-place patches), `handoff/2026-11-01.md` ("Must read next session").

## Why

The surprise idea says Gemma 4 31B trusts its own failing patches because their bug tokens were its own top guesses.
The held-out data already show that other writers' failing patches that edit the same code as the 31B's failing patch
get 100 from the 31B as often as its own (local 31B: 67% vs 54%; leniency own minus these +0.8 [−7.7, +9.1]). One gap
is left: those patches may carry the same wrong tokens. The rename test proposed for this gap is dropped: renaming
mostly changes names around the bug, not the bug, and any rewrite lowers approvals (Kozman et al.).

## Check 1: same place, same or different wrong change

- Set: the held-out issues where the 31B's own patch failed; other writers' failing patches on those issues whose
  edited region overlaps the 31B's: share of 10-line blocks of the original files touched by both patches (overlap
  over union) at least 0.5, as in the 2026-10-28 check (58 patches). Touched lines come from the hunk headers of the
  original-file side, test files removed (the patches the judges saw). The rebuild must give 58 patches, or the
  difference is reported before any score is read.
- Label, fixed before any score is read: for each pair (the 31B's failing patch, the other patch), a blind coder (a
  Claude agent that sees the issue text and the two diffs only, no scores, no writer names, order randomised) answers:
  **same change** (both make essentially the same edit: same code changed in the same way, differences only in names,
  formatting, comments or extra debugging files) or **different change** (the edits differ in what the code does).
  Second label from the same coder: whether the other patch contains the specific line or token the 31B's patch gets
  wrong, if the coder can tell; else "cannot tell". The main analysis uses the first label.
- Secondary, automatic: token Jaccard similarity of the two patches' added lines (whitespace-split, comments and blank
  lines removed); reported as a continuous check on the labels.
- Measures: the local 31B's share of 100s and leniency (score minus the outside judges' mean on the same patch, as in
  `scripts/gemma_sizes_analysis.py`) in each half, the hosted 31B beside it, and the 31B's own failing patches on the
  same issues for reference. 95% intervals from 2,000 bootstrap resamples of issues, seed 0.

Reading rule:

- **Surprise mostly ruled out:** different-change patches get 100 about as often as same-change patches (difference
  under 15 points in the share of 100s) and about as often as the 31B's own failing patches.
- **Surprise or shared belief still possible:** same-change patches get 100 at least 15 points more often than
  different-change patches. Then the bug-token log-probability test is worth running.
- **Too few to read:** fewer than 10 patches in either half. Reported as such.

## Check 2: defect type in the 31 rubber-stamped cases

- Set: the 31 cases in `data/hand-codes/rubber-stamp-cases.md` (the 31B's own failing held-out patches it scored 100
  and at least two outside judges scored 50 or less).
- Code per case, from the outside judges' answers (main defect as in the existing codebook) and the upstream fix:
  **wrong code** (the defect is code the patch adds or changes that is wrong: a wrong keyword, call, condition, value
  or logic in an added line), **missing change** (the patch's added code is right as far as it goes, but a needed
  change is absent: another place, a case not handled, a part of the issue not addressed), or **unclear**. Also the
  added line(s) holding the defect when the code is wrong code.
- Two blind coders (two separate Claude agents, same codebook, no access to each other's codes). Agreement is
  reported (raw and Cohen's kappa); disagreements are settled by reading the case, and the settled codes are the
  result.

Reading rule: if at least two thirds of the settled cases are missing change, the surprise idea has few bug tokens to
work on in Gemma's rubber-stamped failures, and the log-probability test is deprioritised. If at least half are wrong
code, the marked lines are the input the bug-token test needs.

## Predictions (before either check)

- Check 1: different-change patches get 100 nearly as often as same-change ones (difference under 15 points), with
  probability about 0.6.
- Check 2: missing change is the larger group, at least half of the 31, with probability about 0.6.

Outputs: `scripts/derived/same_place_split_2026-11-02.json`, `data/hand-codes/defect-type-coder-{a,b}.csv` and the
settled `data/hand-codes/defect-type.csv`; results in `notes/idea-own-code-surprise-2026-10-28.md` and the changelog.

## Results (2026-11-02, computed after this spec; labels fixed before scores were read)

- Set rebuilt: the 2026-10-28 code (`notes/idea-own-code-surprise-2026-10-28/belief_check.py`) gives the 58 patches
  on 29 issues (`scripts/precheck/same_place_pairs.py`; a first rebuild from the judge prompts' patches gave 102 and
  was discarded before any label or score).
- Check 1 (`scripts/derived/same_place_split_2026-11-02.json`, labels `data/hand-codes/same-place-pairs-labels.csv`,
  one blind Claude coder): same change 22 patches (12 issues), different change 36 (24 issues). Local 31B gives 100 to
  91% vs 53%: +38 points [+18, +56] (hosted 91% vs 50%, +41 [+21, +59]). By the reading rule: surprise or shared
  belief still possible; the bug-token test is worth running. Prediction (difference under 15 points): wrong. But the
  outside judges also score same-change patches far higher (mean 83.0 vs 60.5), and the leniency difference, which
  removes them, is +8.4 [−2.8, +20.2] (hosted +11.9 [−0.3, +25.7]). The 31B's own failing patches on the same 29
  issues: 76% scored 100, outside mean 76.8. The coder's second label (shares the wrong part) partly rests on its
  recollection of upstream fixes, by its own report, so it is not used.
- Check 2 (`data/hand-codes/defect-type.csv`, coders `defect-type-coder-{a,b}.csv`): agreement 26 of 31, kappa
  0.71; 5 disagreements settled by reading the cases (6: name mangling of `__async_capable`, wrong code; 9: a case
  not handled, missing change; 14 and 28: the patch deletes needed code, wrong code with no added line; 18: kept
  unclear). Settled: wrong code 20, missing change 7, unclear 4. 18 wrong-code cases have the defect in 1 or 2 marked
  added lines. By the reading rule: at least half are wrong code, so the marked lines are the bug-token test's input.
  Prediction (missing change at least half): wrong.

## Addendum 2026-11-02, after an advisor discussion (Opus and Fable agents, two rounds), before any of these is computed

Both advisors put the sibling-surprise fix at about 10% and dropped it as the lead. They disagree on the lead fix:
Opus, claim-checking (the judge's approval rests on a false factual claim that a few lines of code can check);
Fable, an existing-test gate before self-review. Opus's objection to the gate, accepted here: PASS_TO_PASS tests are
part of the SWE-bench label (a resolved patch never breaks one) and are chosen with the gold patch, so the gate
measured from the eval logs is an upper bound, not a deployable result. Four checks, thresholds fixed by the advisors:

A. **Claim count** (Opus). Two blind Claude coders on the 31 cases of `data/hand-codes/rubber-stamp-cases.md`: does
   Gemma's answer contain a specific factual claim about the defective construct (the marked `defect_lines` in
   `data/hand-codes/defect-type.csv`, or the deleted code) that is false and that 5 or fewer lines of Python run at
   the base commit with the patch applied could check (signature or keyword existence, attribute name, the value of
   an expression for a given input)? Second code, on the 18 marked cases: does Gemma's answer explicitly endorse the
   defective line? Agreement raw and kappa; disagreements settled by reading. Rule: 10 or more of 31 → write a spec
   for claim-checking; 6 or fewer → drop it; 7 to 9 → code more of the 31B's failing 100s first. 10 or more of 18
   explicit endorsements → also drop locate-then-judge.
B. **Existing-test flag, upper bound** (both). The 31B's own held-out patches as in the paper (`fresh_judging.load`,
   nine judges). Flag: the eval log (`data/mcsr-runs/{main-a,main-b}/eval_logs/<iid>-eval.txt`) shows a PASS_TO_PASS
   test (SWE-bench Verified, local cache) as failed or errored. Parser handles pytest, Django and sympy formats; a
   patch with under 90% of its PASS_TO_PASS tests found in the log is "unparsed" and reported. Measures: (a) share
   of Gemma's failing 100s that break an existing test; (b) top-quarter pass share with Gemma's score, ties broken by
   "breaks no existing test" then fewer model calls (as in the paper's tie-break). Rule: kill the gate if (b) < 78%;
   support if (a) ≥ 40% and (b) ≥ 80%, and even then it is only an upper bound and a baseline.
C. **Catch table** (both). The 31B's own failing held-out patches that the hosted 31B scored 100 (52). Columns: flag
   B; 12B under 100; 26B-A4B under 100; GLM-4.5 at 50 or below; claim flag from A (on the 31 coded cases); caught by
   none. Rule: if under 40% are caught by at least one signal other than GLM-4.5, the only working fix is a judge from
   another lineage (a limit result, recommend stopping); if "none" is 20 or more, that ceiling is stated.
D. **Population split** (both). All 85 own failing patches, split by whether any other writer's failing patch on the
   issue edits the same place (overlap ≥ 0.5, `scripts/precheck/same_place_pairs.py` method). Leniency of the local
   31B, 12B and 26B-A4B in each group, 2,000 issue resamples, seed 0. Supports "mistakes only the 31B makes" if local
   31B minus 26B-A4B in the no-same-place group is at least +10 with lower bound above 0.

## Results of checks A to D (2026-11-02)

Full table and reading: `notes/fix-debate-2026-11-02.md`. A: 8 of 31 false checkable claims (kappa 0.83; cases 14
and 19 settled), endorsement 18 of 18 → code more cases before deciding on claim-checking; locate-then-judge dropped.
B (`scripts/derived/test_flag_2026-11-02.json`): 33% of failing 100s break an existing test; top quarter 79.4% vs
77.8% with calls only → not killed, not supported; upper bound only. C (`catch_table_2026-11-02.json`): 38 of 52
caught by some non-GLM signal, 13 by none, tests alone 7, claim alone 1. D (`population_split_2026-11-02.json`):
local 31B minus 26B-A4B on the 56 no-same-place patches +6.4 [−3.8, +16.8] → not supported. Codes:
`data/hand-codes/claims.csv` (settled), `claims-coder-{a,b}.csv`.
