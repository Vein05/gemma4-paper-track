# Retrospective repair-trace audit

2026-11-05. Requested by the user after the completed repair result. This specification records a retrospective
audit, written after initial trace inspection and before the reusable summary script. It is not a preregistered
mechanism test. No new model calls, sandbox experiments, or training are part of this audit.

Read the 70 saved trajectories, predictions, labels, gate metadata, and existing result summaries. Recompute
outcomes under the original fallback rule; preserve the published run files. Summarize step use, exit reasons,
and explicit action-format errors. Verify the headline counts against the existing analysis. Read failure and
harm traces manually, with message indexes for evidence. Inspect successful controls before proposing a general
guard. Labels and evaluator logs are offline audit evidence, never inputs to a deployable repair policy.

Read-only server checks confirm the run has finished, compare prediction hashes with local copies, and retrieve
the earlier smoke trajectory for diagnosing the smoke/full discrepancy. Store that copy separately under
`data/audits/repair-trace-2026-11-05/`.

Outputs: `scripts/repair_trace_audit_2026_11_05.py`,
`scripts/derived/repair_trace_audit_2026-11-05.json`, and
`notes/repair-trace-audit-2026-11-05.md`.

Separate gross repair, passing-patch harm, net resolved gain, and between-arm comparisons. Newly computed
statistical comparisons are exploratory and do not replace the original primary test. Missing submissions keep
their original grade, as specified for the run. Do not treat format errors, call counts, or agent statements as
causal proof or estimate additional fixes from apparent proximity to a solution.

Any follow-up must use an issue-independent rule on failing and passing candidates alike, preserve original
results, and be separately specified. The user explicitly excludes individual-issue monkey patches. No new
experiment is launched by this audit.
