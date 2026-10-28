# Spec: breaking Gemma's tie at 100 without a second model

The rules below were fixed on the Mini issues at 2026-10-22 22:10 UTC, before any held-out value of these tie-breaks
was computed. An analysis agent wrote them to `notes/human-interest-2026-10-22/lane-fix/prereg_task2.txt`. This file
copies that text unchanged, with this header added on 2026-10-22, so the release holds it. No model calls, existing
data only. Analysis: `scripts/tie_break.py` → `scripts/derived/tie_break_2026-10-22.json`.

Seen on held-out data before the rules were fixed: the paper's numbers, the second-judge checks, and a comparison of
Gemma's reasoning on its own and other writers' patches (not split by passing and failing).

## Rules as fixed (verbatim)

```
Task 2 tie-breakers, fixed 2026-10-22T22:10Z from the Mini issues only, before any held-out tie-breaker value was computed.
(Seen before this point on held-out data: the paper's numbers and Task 1 second-judge gates; the rationale lane's
q1_features_heldout.json header, which compares Gemma's reasoning on its own vs other writers' patches, not pass vs fail.
The rationale lane's q5_tiebreak outputs were NOT read.)

Rule for all three: rank Gemma's own patches by Gemma's 0-100 score; inside equal scores, rank by the tie-breaker.
Remaining ties are broken at random (expected value). Gate metric as in Task 1: precision at 25% and 50% acceptance
minus plain Gemma's (60.9%), 95% interval from 2,000 resamples of held-out issues (seed 0); also Bonferroni (3) 98.3%.
A tie-breaker works if the lower bound of its gain at 25% acceptance is above 0.

1. Concern words (a priori, the natural "read its words" fix): fewer concern words in Gemma's written reasoning ranks
   higher. Count = concern_all from lane-rationales/feats.py. Mini, inside the tie at 100 (142 patches): AUROC 0.527
   [0.428, 0.616]. Expected to fail.
2. Reasoning length (best of 15 rationale features on Mini): shorter written reasoning ranks higher (word count of the
   reasoning without the SCORE line). Mini inside the tie: AUROC 0.621 [0.475, 0.751].
3. Agent steps (best agent-run feature on the 32 tied Mini matched-harness patches): fewer agent steps (n_calls in the
   trajectory) ranks higher. Mini inside the tie: AUROC 0.731 (32 patches, 20 passing).
Frozen variant: accept Gemma=100 patches whose tie-breaker is at or below a cut set on the Mini patches to accept
25% (50%) of them (192 Mini patches for 1-2; 42 matched-harness Mini patches for 3), applied unchanged to held-out.
```

## Notes added after the test

- "Agent steps" counts model calls (`n_calls`), so the paper says "model calls".
- The 98.3% Bonferroni intervals are in `notes/human-interest-2026-10-22/lane-fix/out/task2_heldout.json`;
  `scripts/tie_break.py` reports the 95% intervals.
- The rule "Gemma scores 100 and the run used at most 9 model calls" is the deterministic form of the frozen 25% cut
  (the Mini cut is 9 calls).
- The 16 second-judge checks in the same script are not part of these rules. Their median answers the choice of the
  three checks in the paper's table, which were picked after their AUROCs were seen.
