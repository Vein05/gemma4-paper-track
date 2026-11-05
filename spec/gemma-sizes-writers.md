# Spec: Gemma 4 12B and 26B-A4B as patch writers on the held-out issues (pilot)

Written 2026-11-01, before any agent run of either size. The user's OK for the pilot on the lab A100: 2026-11-01
("let's do the pilot first, and use a100 ... make sure the images are done first and then we run it"). This spec covers
the pilot. The full run and the judging get their own addenda here before they start. Terms follow `GLOSSARY.md`.

Background: `notes/fix-self-review-2026-11-01.md`, `notes/direction-debate-2026-10-28.md` (where this experiment was
ranked first) and `todo.md` item 1.

## Why

Gemma 4 31B gives the top score to 61% of its own failing held-out patches. The 12B and 26B-A4B, judging the 31B's
patches, show little of this extra trust (+0.4 [−6.8, 7.4] and +3.9 [−4.1, 11.8], `spec/gemma-sizes-judges.md`).
Nobody has measured whether each of them trusts its own failing patches. If each size trusts its own and not its
siblings', the rubber-stamping belongs to every Gemma 4 model judging itself. If only the 31B does, it belongs to one
checkpoint. This needs patches written by the 12B and 26B-A4B on the same issues.

## Order

The 26B-A4B first: it alone can answer the question with the 31B, it is the cell nobody has measured, and a stronger
writer is less likely to leave only obviously wrong failing patches. The 12B pilot runs after it, on the same issues
and images, if the user agrees.

## Issues

- The 193 held-out issues (first 200 of the fixed order in
  `data/public/swe-bench-verified-control-fresh/sample.json`, minus the 7 whose reference patch did not resolve on
  Magnolia): `data/sizes_writers_heldout193.json`.
- Pilot: the first 20 of these, `data/sizes_writers_pilot20.json` (django 8, matplotlib 4, sympy 3, astropy 2,
  requests 1, pytest 1, scikit-learn 1). The pilot's patches count toward the full run: the runner skips finished
  issues.
- Images: each issue's SWE-bench image is pulled once into `SIF_DIR` (`<workdir>/swe-env/sif`) before the
  agents start. Docker Hub allows the lab server about 100 pulls an hour.
- Reference check on the A100: the pilot issues' reference patches are graded here too, since the 31B's labels came
  from Magnolia. An issue whose reference patch fails here is reported, and its label for these sizes is not used.

## Writers

Same agent and settings as the 31B's runs (`spec/fresh-replication.md`): mini-SWE-agent 1.7.0, its
`extra/swebench.yaml` unchanged (250 steps, temperature 0, 60 s command timeout), one attempt per issue, thinking off,
writable Apptainer sandboxes of the current `swebench/sweb.eval.*` images (`--fakeroot --ignore-subuid`, as in the
2026-10-05 lab validation). Runner: `scripts/run_gemma_mini.py`, unchanged except that the served model name and the
checkpoint recorded in `run.json` come from `SERVED_MODEL` and `MODEL_ID`, and sandboxes are built from the images in
`SIF_DIR`. Script: `scripts/lab/sizes_writers.sh` (server folder `<workdir>/gemma4-paper-track/sizes`).

- Gemma 4 26B-A4B: `google/gemma-4-26B-A4B-it` revision `4d7ae498`, bf16 weights served with vLLM's fp8 quantization,
  eager mode, CUTLASS fp8 kernel off (the A100 settings that worked for judging on 2026-10-28). Google publishes no
  4-bit checkpoint of it, so its precision differs from the 31B's.
- Gemma 4 12B: `google/gemma-4-12B-it-qat-w4a16-ct` revision `1d2c2d7f`, the same 4-bit format as the 31B.
- vLLM 0.30.0 on the lab A100 (the 31B ran vLLM 0.31.0 on an L40S): context 131,072, 8 sequences, prefix caching,
  GPU memory 0.90, 5 agent workers. The run does not start if more than 2 GB of GPU memory is in use.

Differences from the 31B's runs, recorded as limits: GPU and vLLM version, the 26B-A4B's precision, and grading on
the lab server instead of Magnolia.

## Stop rule (fixed before the pilot)

From the 2026-10-28 adversarial review: no full run for a size if, on its 20 pilot issues, it resolves under 10%
(fewer than 2) or fewer than 85% of runs (fewer than 17) end with a submitted, non-empty patch. Also reported, not
part of the rule: median minutes per issue, model calls, exit statuses, and the 31B's result on the same 20 issues.

## Predictions (before the pilot)

Uncertain; no measured SWE-bench result for either size was found (third-party figures for the 26B-A4B conflict).
26B-A4B: passes the rule, resolving 20 to 50% of the pilot. 12B: about even odds of passing. Median time per issue:
under 15 minutes for both on the A100.

## Later steps (each gets an addendum before it starts)

- Full run on the other 173 issues for each size that passes, then grading.
- Judging: the three Gemma sizes served locally and the eight outside judges, with the measures of
  `todo.md` item 1, including the floor check (at least 40 own failing patches with an outside mean of at least 40).
- W&B: project `gemma4-paper-track`, group `gemma-sizes-writers`, logged from this Mac. Changelog entry per run.

## Addendum 2026-11-01 21:35 UTC, after the reference check, before any agent run

The reference check on the A100 resolved 19 of 20 pilot issues. `psf__requests-1724` fails here: its test
`test_mixed_case_scheme_acceptable` makes a live HTTPS request, and the lab server's network gives
`SSL: CERTIFICATE_VERIFY_FAILED` (the same issue resolved on Magnolia). The agents still run on all 20 issues. In the
stop rule, "resolved" counts only the 19 issues whose reference patch resolves here (at least 2 of 19); "submitted"
still counts all 20 (at least 17 of 20). In the later judging, the sizes' labels on `psf__requests-1724` are not used.

## Addendum 2026-11-02 00:39 UTC: the 12B pilot, before it starts

The user agreed to the 12B pilot on 2026-11-02 ("can we run the smaller model on the side too?"). It cannot share the
GPU with the 26B-A4B's server (73.3 of 80 GB in use; the 12B's weights are 9.6 GB). It starts as soon as the 26B-A4B
pilot's agents finish and its vLLM server stops (under 2 GB in use), and its agents run while the 26B-A4B's patches
are graded on CPU (128 cores; each sandbox gets its own folder). Same 20 issues, images, settings and stop rule as the
26B-A4B, including the `psf__requests-1724` rule above. Timing is reported but is not part of the stop rule; the
12B's minutes per issue may be a little slower than they would be alone because grading runs at the same time.

## Addendum 2026-11-02 04:20 UTC: 26B-A4B pilot result (recorded before any full run)

Resolved 8 of the 19 usable issues, submitted 19 of 20: the 26B-A4B passes the stop rule. Prediction (20 to 50%
resolved): met. Prediction (median under 15 minutes): missed, 15.8. Observed limits to carry into the full run and the
paper: about 8% of model calls ran past LiteLLM's 600-second client timeout and were retried with the same prompt
(43 timeouts), so in effect the 26B-A4B's replies are capped at what it generates in 600 seconds (about 20k tokens),
a cap the 31B never reached; one issue ended with ContextWindowExceededError after the agent repeated one reply 50
times. A full 26B-A4B run needs the user's OK and a choice, written here before it starts: the pilot's settings
unchanged, or a reply-length cap or bf16 serving.
