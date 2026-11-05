# Spec: a rubber-stamping check with a free local judge (Qwen3-32B), and Qwen3-32B as Gemma's reviewer

Written 2026-11-03, before Qwen3-32B scored any SWE-bench Lite or LiveCodeBench patch. Exploratory; it decides
whether the paper can lead with a check any developer can run (`notes/committee-2026-11-03/README.md`, red-team
section; `notes/plan-explain-check-fix-2026-11-03.md`, part 2). Run approved by the user ("start the qwen run").

## Already seen (held-out issues, development)

Qwen3-32B's written scores on the held-out issues exist (`fresh_qwen3-32b-local.jsonl`, spec/judge-probe.md addendum
7). The red-team reviewer computed, with Qwen3-32B as the only outside judge: Gemma +19.0 [+8.8, +28.2]; none of the
five other self-judging models flagged. These numbers are development data, not confirmation.

## Runs (lab A100, user's OK)

Qwen3-32B (bf16, the snapshot used for the held-out run), served by vLLM at 32,768 tokens, thinking off, the paper's
judging prompt, as in `scripts/lab/run_qwen_retry.sh`: SWE-bench Lite (`lite_p1.jsonl`, 1,478 prompts) and
LiveCodeBench (`lcb_p1.jsonl`, 839 prompts); first pass at 3,000 tokens, then unparsed answers redone at 8,000.
Chain `scripts/lab/open_panel_chain.sh`, outputs `probe/lite_qwen3-32b-local.jsonl`, `probe/lcb_qwen3-32b-local.jsonl`.
No pilot: the same model, prompt and settings already ran on the held-out issues.

## Measures

Leniency as in the paper (judge's score minus the panel's mean on the same patch; Gemma's own failing patches against
other writers' failing patches on the same issues), with the panel = Qwen3-32B alone. Patches written by Qwen-family
models (held-out: Qwen3-Coder; Lite: Qwen3-Coder-30B and SWE-Fixer-Qwen2.5-72B) are left out of this comparison,
because the paper drops panel judges of the writer's family and Qwen3-32B would be the only one. 95% intervals, 2,000
issue resamples, seed 0.

1. **Check.** Gemma's leniency with Qwen3-32B as the panel on held-out, Lite, LiveCodeBench. On held-out, the same for
   each of the five other self-judging models. Reported beside it: the four-judge open panel (Qwen3-32B, gpt-oss-20b,
   Qwen3.5-9B, GLM-4.7-Flash; family rule applied) and the paper's paid panel.
2. **How many patches.** For k = 10, 20, 30, 50, 80 own failing patches (issues resampled until k are reached, 1,000
   draws), the share of draws in which Gemma is flagged (bootstrap interval above 0, 500 resamples inside each draw),
   per set; and the share in which each of the five other models is flagged on held-out.
3. **Qwen3-32B as Gemma's reviewer.** On Gemma's own patches: AUROC of Qwen3-32B's score minus AUROC of Gemma's
   score, with interval; share passing in the top quarter by Qwen3-32B's score, against Gemma's score (61% among its
   ties), fewer model calls (78%) and GLM-4.5 (84%) as reported in the paper.

## Reading, fixed now

- **Check works with one free judge:** Gemma's interval above 0 on all three sets, and none of the five other models
  flagged on held-out.
- **Check needs a larger panel:** otherwise; the paper then reports the smallest panel that met the rule, or the
  paid panel.
- **Patches needed:** the smallest k at which Gemma is flagged in at least 80% of draws on every set, with the false
  flag rate of the five other models at that k.
- **Local reviewer helps:** Qwen3-32B minus Gemma AUROC interval above 0 on held-out and on Lite (LiveCodeBench
  reported). Otherwise the paper does not offer it as a method.

## Logging

Score files copied to `data/lab-runs/open-panel-check/`, also as `scripts/derived/lite_qwen3-32b-local.jsonl` and
`lcb_qwen3-32b-local.jsonl`; analysis `scripts/open_panel_check.py` → `scripts/derived/open_panel_check_2026-11-03.json`;
W&B group `check` (one run for the judge scores); changelog entry.
