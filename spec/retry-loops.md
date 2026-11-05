# Spec: repeated failing tool calls in existing agent runs (2026-10-05)

Written before any loop statistic was computed. Data formats were inspected (file lists only) to write the
definitions. No model calls; existing public runs only.

## Question

When a tool call gives a result that does not help, how often does the agent make the identical call again
with the identical result, and how much of the run does that use? Does this happen beyond the known
`edit_file` parser bug in the competition harness? Is it specific to Gemma 4 or does another model in the
same harness on the same tasks do it as often?

Purpose: decide whether the recovery-gap result (an instruction to "retry once, then switch to another
route" brought a warned agent to its clean-task ceiling; `../recovery-gap/changelog/2026-09-18.md`, a
40-cell probe on one model) has a natural target in coding agents. This analysis is descriptive. It does not
test any intervention.

## Data (all public)

| Group | Model | Harness | Source | Runs |
|---|---|---|---|---|
| G1 | Gemma 4 31B (4-bit, vLLM `gemma4` parser) | competition harness | `rishaviitd/kaggle.gemma.coding.agent` traces (GitHub) | 76 |
| G2 | Gemma 4 31B-it | SWE-agent | HF `n-pelleriti/alphadiana-sweagent-gemma4-directllm-20260727` | 50 |
| G3 | Qwen3.5-27B | SWE-agent | HF `n-pelleriti/alphadiana-sweagent-qwen35-directllm-20260728` | 49 |
| G4 | Gemma 4 31B-it | opencode (2 runs), zeroclaw, openclaw | HF `n-pelleriti/alphadiana-swe-mini-*-gemma4-*` | up to 50 each |
| G5 | Qwen3.5-27B | openclaw | HF `n-pelleriti/alphadiana-swe-mini-qwen35-27b-20260729` | up to 50 |

G2–G5 are on the same 50 SWE-bench Verified Mini tasks. G2 vs G3 is the main model comparison (same
harness, same tasks). G4 vs G5 is a second comparison where the openclaw runs overlap. G1 is competition
data: analysed on this machine only, and only counts are saved.

Labels: `data/public/gemma4-own-attempts/attempts.jsonl` for Gemma (G2, G4); SWE-bench reports in the
Qwen datasets for G3, G5; per-task result files for G1.

## Definitions

- **Call**: one tool call by the agent: tool name plus arguments, or for SWE-agent the `action` string.
  Canonical form: arguments as JSON with sorted keys, whitespace runs collapsed to one space, stripped.
- **Result**: the observation returned for the call, normalized the same way, with timestamps, durations,
  temporary paths and hex ids replaced by placeholders.
- **Futile repeat**: call t+1 has the same canonical form as call t and its result equals the result of
  call t. The environment returned nothing new.
- **Loop**: three or more consecutive calls with the same canonical form and the same result (two or more
  futile repeats in a row).
- **Pagination exclusion**: calls whose purpose is to move a view (SWE-agent `scroll_down`, `scroll_up`)
  are not counted even if identical; their results normally differ anyway.
- **Error-like result** (secondary measures only): a result matching the per-harness error rules in
  `scripts/retry_loops.py` (`ERROR_PATTERNS`): explicit error status fields where the harness has them,
  otherwise tool error strings (edit target not found, missing parameter, file not found, command not found,
  Python traceback, non-zero exit code shown by the harness).
- **Loop cause** (descriptive): the error class of the first result in the loop. `parser_merge` = the
  competition harness's "mandatory input parameters are not present" on `edit_file`; other classes as in
  `ERROR_PATTERNS`; `no_error` if no rule matches.

## Measures (per group; 95% intervals by bootstrap over tasks, 2,000 resamples)

Primary:
1. Share of unresolved runs that contain a loop whose cause is not `parser_merge`.

Secondary:
2. Share of all runs with any loop; share of unresolved and of resolved runs with a loop.
3. Share of all calls in a run that are futile repeats (mean over runs; and pooled).
4. P(next call identical | error-like result) and P(next call identical | other result).
5. Whether the run's last call is inside a loop (the loop ran into the budget or the end).
6. Loop causes, counted by loop and by run.
7. G2 vs G3 difference in measures 1–3 (and G4 openclaw vs G5 where tasks overlap).

## Decision rule (fixed before computing)

- **Go** (design a directive study for coding agents): measure 1 is at least 15% pooled over Gemma groups
  G1, G2, G4, and at least 10% in at least two of the harnesses.
- **Section only** (keep as a paragraph next to the recovery-gap result): measure 1 between 5% and 15%, or
  at least two thirds of loop runs are `parser_merge`.
- **Drop**: measure 1 below 5%.

Not a gate, used for framing: if G3 (Qwen) shows loops at a similar rate to G2, the behaviour is general
rather than Gemma-specific; if Gemma is much higher, it is a Gemma property.

## Known limits

- Loops in unresolved runs are not proof that loops cause failure: hard tasks produce both. Resolved vs
  unresolved comparisons are descriptive.
- Harnesses differ in budgets and in how they report errors; comparisons across harnesses are rough.
  The model comparison uses the same harness only.
- Identical-result matching misses repeats whose result differs only in noise not covered by the
  normalization; a hand check of 20 loops and 20 non-loop repeats is part of the analysis.
- One sample per task per run in the AlphaDiana data; 50 tasks, two repositories (django, sphinx).
