# Spec: fixing Gemma 4's own-patch check without training or a second model (2026-10-05)

Written before any of the signals below was computed. Data as in `spec/own-patch-mechanism.md`: Gemma 4's own
patches on the 50 SWE-bench Verified Mini issues (four harnesses, up to 6 per issue), Gemma's reasoning-first 0–100
scores with reasoning off (`derived/selfpref_gemma4-31b.jsonl`) and thinking on (`..._gemma4-31b-think.jsonl`).
No model calls. Script: `scripts/self_check_fix.py`.

Target: AUROC for flagging Gemma's own failing patches (all own patches with both Gemma scores). Baseline S0 =
Gemma's reasoning-off score: 0.636 on the 333-patch set. Reference (not a fix, needs a second model): mean of the
eight outside judges on the same patches.

Why these signals: the deficit is across issues (Gemma rates its own patches high on issues it cannot solve), so a fix
must carry issue-level information. Scaling or "be stricter" prompts shift all scores and cannot change AUROC.

## Signals (all from Gemma alone)

- S1 attempt agreement: for each own patch, the mean Jaccard similarity of its normalized changed lines with Gemma's
  other patches on the same issue. Patches on issues with no other Gemma patch get the median of S1 (neutral).
- S2 two-sample self-consistency: mean and minimum of Gemma's reasoning-off and thinking-on scores for the patch.
- S3 within-issue relative score: Gemma's score minus the mean of Gemma's scores on its other patches for that issue
  (0 if none). Diagnostic: it removes the issue level, so it should do well within issues and poorly across.
- Combinations, fixed in advance (no fitting): C1 = z(S0) + z(S1); C2 = z(mean S2) + z(S1). z = standardization over
  the own-patch set.

## Measures

AUROC of each signal and combination on Gemma's own patches, with 2,000 issue-bootstrap intervals; difference from S0
with interval. Same-issue and different-issue pair accuracy (as F1) for S0, C1, C2.

## Reading rule

Primary: C1 vs S0. A fix is shown if the difference is ≥ +0.05 with the interval's lower bound > 0. Report how much of
the S0-to-outside-judges gap it closes. C2 and single signals are secondary.

## Cost in the competition setting (stated, not measured)

S1 needs k agent attempts per task (k × agent time on a sequential scorer); S2 needs two judge calls per patch; S0 one.
The attempts here come from different harnesses, so their diversity may exceed that of k samples from one agent —
a limit on transfer.

## Deviations

None yet.
