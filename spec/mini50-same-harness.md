# Spec: Gemma 4's own-patch check on the original 50 issues, patches written by mini-SWE-agent

FROZEN 2026-10-06 00:20 CDT, committed to the release repo before the agent run. Secondary to
`spec/fresh-replication.md`; terms follow `GLOSSARY.md`.

## Why

The self-judging gap (+0.135 [0.060, 0.210]) was found on the 50 SWE-bench Verified Mini issues with Gemma patches
from four harnesses (SWE-agent, openclaw, opencode, zeroclaw), while every control patch came from mini-SWE-agent. The
fresh-issue run separates harness and model on new issues. This run does it on the same 50 issues, so a change in the
gap cannot come from the issues: only the harness (and the agent run) differs from the original Gemma patches.

## Patches

- Issues: the 50 Mini issues (`data/public/gemma4-own-attempts/swe-bench-verified-mini.parquet`; django 25,
  sphinx 25).
- Agent, model, settings, sandbox, compute and grading exactly as in `spec/fresh-replication.md` (mini-SWE-agent
  v1.7.0, its SWE-bench config unchanged, `gemma-4-31B-it-qat-w4a16-ct` revision `52f3f65b` on one Magnolia L40S,
  temperature 0), one attempt per issue: `run_pilot.sbatch` with `ISSUES=ids:<the 50>`, `OUT=runs/mini50`.
- Controls: the existing control patches and labels for these issues (`data/public/swe-bench-verified-mini-control/`).
- Labels: Magnolia's grading, with the same condition as the fresh-issue spec (cross-checked before analysis while
  Magnolia's grading check stands at 26 of 30).

## Judges and measures

- Same nine judges, prompt (`Q_P1`), settings and parser as `spec/self-judging-replication.md`; judging runs later
  from the Mac, together with the fresh-issue patches.
  The re-ask of unparsed answers uses 8,000 output tokens (addendum 2026-10-06 15:05 to `spec/fresh-replication.md`,
  added after the freeze). The Mini-50 control patches keep their scores from the original study (3,000 tokens).
- Primary: Gemma's self-judging gap on its new mini-SWE-agent patches for these 50 issues, defined as in
  `scripts/self_judging_replication.py`, 95% interval from 2,000 bootstrap resamples of issues.
- Reading rule (50 patches, so the interval will be wide):
  - lower bound > 0: the deficit appears with mini-SWE-agent patches on the original issues; harness alone does not
    explain it.
  - interval includes 0 and the point estimate is below half the original (0.068): consistent with the harness
    explanation; not a test of it on its own (low power).
  - otherwise: inconclusive; report the estimate with its interval.
- Secondary: rubber-stamp rate on own failing patches (share scored 100) in the new and the original Gemma patches.
- This run is reported as secondary evidence next to the fresh-issue result, never in place of it.

## Order and cost

Queued to start only after the fresh-issue main run's second job has started (`sbatch -d after:<job>`), so it does not
take a GPU from it. No API cost for the agent runs; judging 9 × 50 new patches = 450 calls, about $0.35 (the control
patches were already judged in the original study).
