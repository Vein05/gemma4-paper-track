# Spec: does Gemma trust the change or the author? (belief vs recognition)

Written 2026-11-03, before the analysis below was run on either set. Exploratory; it decides which explanation the
paper gives and which fix is tried next (`notes/winner-gap-2026-11-03.md`). No GPU, no API credit: it uses the
written scores of the paper's judges that already exist.

## Question

Gemma 4 31B is lenient on its own failing patches (paper's measure: held-out +16.6, SWE-bench Lite +17.8). Two
explanations predict different things for other writers' failing patches:

- **Belief.** Gemma trusts changes it would make itself, whoever wrote them. Its extra trust in another writer's
  failing patch rises with how close that patch's edit is to Gemma's own edit on the same issue, and Gemma's own
  failing patches are trusted about as much as other writers' failing patches that make nearly the same edit.
- **Recognition.** Gemma trusts its own writing as such. Its own failing patches stay above other writers' failing
  patches that make nearly the same edit.

Earlier hand-coded hint, held-out only: other writers' failing patches that edit the same place get 100 about as
often as Gemma's own (66% vs 61%). Not replicated; not on the paper's measure.

## Data

- Held-out issues: the 957 patches scored by all nine judges (`fresh_judging.load`, runs main-a and main-b).
- SWE-bench Lite: the patches scored by the seven Lite judges (`per_writer_leniency.load_rows`).
- Scores: written scores of the paper's judge (hosted Gemma 4 31B) and of the outside panel, exactly as in
  `scripts/per_writer_leniency.py`. Gemma's excess score on a patch, E = Gemma's score minus the mean score of the
  outside panel on that patch (the paper's leniency is mean E on own failing minus mean E on other failing).
- Patch text: the diff each judge saw (test files already removed).

## Edit similarity, fixed now

For a diff, its edit set is the set of (file path, "+" or "−", line with whitespace stripped) over changed lines in
files that already exist (files created by the patch, `--- /dev/null`, are left out; empty lines are left out). The
similarity of a patch to Gemma's patch on the same issue is the Jaccard index of the two edit sets. Issues without a
Gemma patch, or where Gemma's edit set is empty, are left out. A patch "makes Gemma's edit" if similarity ≥ 0.5.

## Measures

Failing patches only. Intervals: 95%, 2,000 resamples of issues, seed 0.

1. **Similarity effect.** Among other writers' failing patches: mean E for those that make Gemma's edit minus mean E
   for those that do not.
2. **Own vs same edit.** Mean E on Gemma's own failing patches minus mean E on other writers' failing patches that
   make Gemma's edit (issues with both).
3. Reported beside them: the paper's leniency on the same issues; counts of patches in each group; the same two
   measures with the cut-off at 0.3 (reported only).

## Reading, fixed now (per set; the explanation needs both sets)

- **Belief supported:** measure 1's interval is above 0, and measure 2's interval includes 0 or its point estimate is
  at most half the paper's leniency on the same issues.
- **Recognition supported:** measure 2's interval is above 0 and its point estimate is more than half the paper's
  leniency on the same issues.
- **Inconclusive:** anything else, or fewer than 20 other-writer failing patches that make Gemma's edit in that set.
- If the two sets disagree, the paper does not state either explanation.

## Logging

Script `scripts/belief_vs_recognition.py` → `scripts/derived/belief_vs_recognition_2026-11-03.json`; W&B group
`explanation`; changelog entry.

## Addendum 1 (2026-11-03, after the main result, before these two tests were run)

Main result: belief supported on SWE-bench Lite, inconclusive on the held-out issues (same direction); recognition
supported on neither. The strongest alternative: edits close to Gemma's may be the common fix many writers make, so
Gemma would trust conventional fixes, not its own beliefs. Two tests, same similarity, cut-off 0.5, failing patches,
2,000 issue resamples, seed 0. Results are not logged to W&B (user, 2026-11-03).

**Test A, other reference edits.** For each writer R, the pool is the failing patches of writers other than R and
Gemma. Effect(R) = Gemma's E on pool patches that make R's edit minus on those that do not. For R = Gemma the pool is
every other writer's failing patches (the main result's measure 1). Report each effect and Gemma's effect minus the
mean of the other writers' effects (Δ), per set.

- **Gemma's own edit:** Δ's interval above 0.
- **Common fix:** Δ's interval includes 0 and the mean of the other writers' effects has its interval above 0.
- **Inconclusive:** anything else.

**Test B, each judge on its own edits (held-out only; on Lite no writer other than Gemma is a judge).** For each of
the six judges that also wrote patches (Gemma 4 31B, Qwen3-Coder, gpt-oss-120b, GLM-4.5, Kimi-K2, Llama-4-Maverick):
its excess E_k (its score minus the mean of the panel without it, without Gemma, and without judges of the patch
writer's family, as in `per_writer_leniency.py`) on other writers' failing patches that make its own edit minus on
those that do not; and its own failing patches minus the same-edit ones. Report each, and Gemma minus the mean of the
other five for the first measure.

- **Specific to Gemma:** that difference's interval above 0.
- **Every judge trusts its own edits:** the difference's interval includes 0 and the mean of the other five has its
  interval above 0.
- **Inconclusive:** anything else.

The paper states the belief explanation only if the main test supports belief on both sets and Test A does not read
"common fix" on either set.
