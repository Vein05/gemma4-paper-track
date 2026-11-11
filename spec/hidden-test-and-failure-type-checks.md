# Checks of issue difficulty, failure type and one interval (exploratory, 2026-11-11)

Written before any of the numbers below were computed. All three analyses are exploratory. They were chosen after
the paper's results were seen, in answer to a reviewer's objections. Rough recounts by an earlier agent had also been
seen, unverified:

- 48 issues that no public entry solves hold 1,405 of the 4,961 failing patches that change code; without them the
  wrong-fix share is 67%; the rise with model strength "holds in each of five difficulty bands".
- Pooled over five equally strong writers, Gemma gives 100 to 64% of 239 wrong fixes and to 36% of 159 patches that
  break a listed test.
- The interval for the drop in correct patches broken by the labelled repair is 4 to 24 (the supplement says 3 to 25).

No model calls, no GPU, no network. Nothing is trained or judged, so nothing goes to W&B. Intervals are 95%, from 2,000
bootstrap resamples of issues with `numpy.random.default_rng(0)`, as in `scripts/failure_census.py` and
`scripts/matched_writers.py`.

## 1. Wrong fixes across public models, holding issue difficulty fixed

Script `scripts/wrong_fix_difficulty.py`. It reads `data/public/swe-bench-verified-failure-census/rows.jsonl` with the
definitions of `scripts/failure_census.py`: the 32 entries with at least 490 reports, failing patches that change code,
a wrong fix when no listed other test fails, an entry's strength as its share of the 500 issues solved.

1. Reproduce the census: 71% overall, 64% for entries solving 40% to 60%, 81% for entries solving 70% or more, rank
   correlation 0.80 over the 30 entries solving at least 40%. If any of these differs, stop and report the difference.
2. The overall share, the two group shares and the rank correlation without the issues that no entry solves, and
   without the issues that 3 or fewer of the 32 entries solve (under 10%).
3. Five difficulty bands by how many of the 32 entries solve the issue: 0, 1 to 7, 8 to 15, 16 to 23, 24 to 32. In
   each band: the wrong-fix share for the entries solving 40% to 60% and for those solving 70% or more, their
   difference, and the rank correlation across the 30 entries (an entry is left out of a band where it has fewer than 5
   failing patches that change code), with intervals from resampling the band's issues.
4. The issue held fixed. (a) For every issue where both groups have a failing patch that changes code, the stronger
   group's wrong-fix share minus the weaker group's; the mean over issues. (b) A linear probability model over every
   failing patch that changes code from the 30 entries: wrong fix on the entry's share solved, with a fixed effect for
   each issue (the within-issue slope), beside the same slope without fixed effects. Slopes are reported per 10 points
   of share solved.

Reading. The rise holds once the issue is fixed if the within-issue difference (4a) and the fixed-effect slope (4b)
have intervals above zero and are at least half of their counterparts without the issue fixed (the 17-point group
difference and the slope without fixed effects). It shrinks if the interval is above zero but the value is less than
half. It disappears if the interval includes zero. The 71% holds if the share without never-solved issues and without
issues solved by 3 or fewer entries stays above 60% (still most failing patches); it does not hold if it falls below
50%. The band table is descriptive; the rise is said to hold within a band only if that band's interval for the group
difference is above zero.

## 2. Gemma's top score by failure type, within writer

Script `scripts/failure_type_top_score.py`. Patches: the failing held-out patches of `scripts/derived/matched_patches.jsonl`
that all nine judges scored (as in `scripts/matched_writers.py analyze`) and that change code (`patch_class` on the
patch the judges saw, as in `scripts/code_changing_patches.py`). Failure types for the five equally strong writers in
the census (Gemini 2.5 Pro, o3, o4-mini, GPT-5 mini, GPT-5 nano) come from the census row for the same entry and
issue: a wrong fix when the issue's tests fail and no listed other test fails, otherwise a patch that breaks a listed
test. Rows where the census and the judged label disagree about failing are counted and left out. For Gemma's own
patches, the split is the one of `scripts/failure_types.py` (44 wrong fixes, 30 that break a listed test, October
scores), and the same split is repeated on the November scores of `matched_writers.py` where test outcomes exist.
GLM-4.5 and Kimi-K2 are included only if test reports for their held-out patches exist under `data/`.

For each writer: n wrong fixes, n that break a listed test, Gemma's share of 100 scores in each, Gemma's mean score,
the outside judges' mean score (judges outside Gemma's family and the writer's, as in `matched_writers.py`) and the
outside judges' share of 100 scores (each outside judge's share, averaged). Then the difference wrong fix minus
breaks a listed test: pooled over the five writers; averaged over writers; averaged within model family first (Google,
OpenAI). Intervals resample issues. Last, a count of the patches that break a listed test and that Gemma scores below
50: how many fail every issue test and fail at least half of the listed other tests (an obvious crash).

Reading. Gemma gives the top score more to wrong fixes on other writers' patches if the family-balanced within-writer
difference has an interval above zero. If the same difference for the outside judges is of similar size, this is true
of judges in general and not specific to Gemma. If the within-writer difference includes zero, the pooled difference
is a writer-mix effect and the claim rests on Gemma's own 44.

## 3. Interval for the labelled repair

Script `scripts/labelled_repair_interval.py`. It builds the per-patch table of `scripts/labelled_repair_analyze.py`
(run with W&B off) and computes the paired difference in correct patches broken, the repair with the tests shown
minus the labelled repair (20 minus 7), with the interval as `boot` in that script computes its others: per-issue sums,
2,000 resamples of the 99 issues, seed 0. It is reported beside the supplement's 3 to 25. Reading: whichever interval
the script writes is the reproducible one; a different supplement number is a typo to fix.
