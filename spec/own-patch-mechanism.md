# Spec: why does Gemma 4 rate its own failing patches high? (2026-10-05)

Written before the analyses below were run. Inputs already exist except the thinking-on ratings (P1).
Context: `notes/committee-2026-10-05/README.md` (skeptic's corrections), `spec/self-judging-replication.md`.

Data: the 388 patches on the 50 SWE-bench Verified Mini issues (174 Gemma 4 own patches from four harnesses, 214
patches from six mini-SWE-agent control writers), reasoning-first 0–100 scores from nine judges
(`derived/selfpref_<tag>.jsonl`), labels from SWE-bench evaluation. Issue-clustered bootstrap, 2,000 resamples, seed 0.

Fact found while writing this spec (format check, not an outcome): Gemma's patches are much smaller than the control
writers' (mean 7.7 vs 72.7 added lines; 0 vs 81 patches adding new files; 4% vs 58% multi-file). Size is a
confound for every own-vs-other comparison.

"Outside judges" for Gemma = the eight other judges, excluding none (no other Gemma-family judge), as in the
replication. "Self minus outside" = Gemma's measure minus the mean of the outside judges' measures.

## F1. Same issue vs different issues (free)

Pair accuracy over Gemma's own pass/fail patch pairs (ties count half), split into pairs from the same issue and
pairs from different issues. Self minus outside for each split.
Reading rule: "ranks its own attempts but cannot tell when none works" is supported if the same-issue difference has
an interval including 0 and |point| ≤ 0.05, and the different-issue difference has a lower bound > 0.

## F2. Size-matched leniency (free)

Leniency = Gemma's score minus the outside judges' mean, on failing patches. Compare Gemma's own failing patches with
control failing patches matched on size: each own failing patch is paired with the control failing patches in the same
size stratum (added+removed lines: 1–5, 6–15, 16–40, >40; and single-file only). Report the leniency difference
(own minus size-matched control) with its interval, next to the unmatched +23.0 [12.7, 33.6].
Also report Gemma's leniency on control failing patches by size stratum (does Gemma favour small patches by anyone?).
Reading rule: the size explanation is supported (and the self-specific claim weakened) if the matched difference is
below half the unmatched difference or its interval includes 0.

## F3. Agreement with its own attempt (free)

For each control failing patch on an issue where Gemma has at least one failing patch: similarity = Jaccard index of
the sets of normalized changed lines (added and removed lines, whitespace collapsed, empty lines dropped) with the
most similar Gemma failing patch on that issue. Primary: Gemma's leniency on control failing patches with similarity
above the median vs at or below it (difference with interval). Control: the same split for each outside judge's
deviation from the other outside judges' mean (should be near 0).
Reading rule: "Gemma accepts fixes that agree with its own wrong fix" is supported if the difference is > 0 with the
interval excluding 0 and the outside-judge control is near 0. If not, agreement is not shown at this sample size.

## F4. Judging others does not predict judging yourself (free, descriptive)

(a) For the six judges that wrote patches: AUROC on other writers' patches (excluding their own family) and the
self-judging gap from the replication; list both, no test (six points).
(b) Each judge's AUROC on Gemma's own patches, with intervals; difference Gemma minus each outside judge. Plus,
as an agent-facing number, precision and recall of accepting Gemma's patches at score ≥ 95 for Gemma and for each
outside judge.

## P1. Thinking on (free tier or ≤ $2)

Gemma 4 31B re-rates all 388 patches with its own reasoning switched on (OpenRouter `reasoning.enabled = true`), same
prompt, temperature 0, 6,000 output tokens. Prefer `google/gemma-4-31b-it:free`; fall back to the paid endpoint
with a $2 ceiling. Output `derived/selfpref_gemma4-31b-think.jsonl`. Unparsed answers re-asked once.
Primary: Gemma's self-judging gap (self drop minus the outside judges' mean drop, outside judges' existing scores),
as in the replication; plus F1 and F2 on the thinking-on scores.
Reading rule: thinking removes the effect if the gap point estimate is ≤ 0.03; it persists if the lower bound > 0.
Anything between is reported as inconclusive.

## Not in this spec

Gemma's QAT checkpoint (A100) and the competition setting (Kaggle agent runs). Decide after these results.
Comment-stripping (only 21 of 174 Gemma patches contain added comments; too few to test).

## Deviations

Record here with date if anything changes after results are seen.

- 2026-10-05, after F1 ran: the F1 reading rule has the sign backwards. "Self minus outside" is negative when Gemma
  is worse, so the intended rule is: the different-issue difference has an upper bound < 0 (Gemma worse than outside
  judges), not a lower bound > 0. The intent (deficit across issues, none within) is unchanged; only the sign in the
  written rule was wrong. Results are reported against the corrected rule and this note.
- F1–F4 use the 333 patches with a score from all nine judges (55 left out for unparsed answers), as in the
  replication.
