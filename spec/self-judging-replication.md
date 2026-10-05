# Spec: does a model judge its own patches worse than other agents' patches? (replication beyond Gemma 4)

Written 2026-10-05, before any model call of this test. Terms follow `GLOSSARY.md`.

## Why

Exploratory finding (not in any earlier spec; computed 2026-10-05 from `derived/selfpref_*.jsonl`): on the 50 SWE-bench
Verified Mini issues, Gemma 4 31B ranks failing below passing patches with AUROC 0.835 on the six control writers'
patches (best of four judges) and 0.640 on its own patches (worst). Outside judges barely change. Difference in
differences +0.154 [0.052, 0.251]. This test asks whether the same holds for other models judging their own patches.
The Gemma result is the reason for the test and is not counted as evidence in it.

## Data (no new data)

The 388 patches already used by `scripts/self_preference.py`: usable Gemma 4 31B patches and the six mini-SWE-agent
control writers' patches on the same 50 issues (`data/public/gemma4-own-attempts/`,
`data/public/swe-bench-verified-mini-control/`), test-file hunks removed, at most 30,000 characters, labels from the
SWE-bench evaluation reports.

## New judges (each is the exact model that wrote one control writer's patches)

| Writer (control) | Judge on OpenRouter | Model card id |
|---|---|---|
| qwen3-coder-480b-a35b-instruct | `qwen/qwen3-coder` | Qwen/Qwen3-Coder-480B-A35B-Instruct |
| gpt-oss-120b | `openai/gpt-oss-120b` | openai/gpt-oss-120b |
| glm-4.5 | `z-ai/glm-4.5` | zai-org/GLM-4.5 |
| kimi-k2-instruct | `moonshotai/kimi-k2` | moonshotai/Kimi-K2-Instruct |
| Llama-4-Maverick-17B-Instruct | `meta-llama/llama-4-maverick` | meta-llama/Llama-4-Maverick-17B-128E-Instruct |

devstral-small-2512 has no matching model on OpenRouter (only the 123B Devstral 2); its patches stay in the data as
another writer but it has no self-judge. Weights served by OpenRouter providers may differ in precision from the
weights that wrote the patches; recorded as a limit.

## Procedure

- One reasoning-first rating (prompt `Q_P1`, temperature 0, 3,000 output tokens) per judge per patch, through
  `scripts/self_preference.py run`, same system prompt and parser as all earlier runs. Reasoning switched off
  (`reasoning.enabled=false`) except gpt-oss (effort "low", +3,000 tokens), as before. Default provider routing,
  provider recorded. The prompt does not say who wrote the patch.
- Unparsed answers are asked once more (same settings); still unparsed → left out (count reported).
- Existing ratings of the four earlier judges are reused unchanged.
- Estimated cost about $2.7 (gpt-oss $0.07, GLM-4.5 $0.94, Qwen3-Coder $0.44, Maverick $0.29, Kimi-K2 $0.95). Stop
  and report if spend passes $4.

## Measures (fixed now)

Judges: the 4 earlier + 5 new = 9. Patch set for AUROC: patches with a parsed score from all 9 judges.
For judge J that wrote patches as writer W (self pairs: the 5 above, plus Gemma 4 31B, reported separately):

- AUROC_J(W) = AUROC of J's score for ranking W's failing patches below W's passing patches (ties count half).
- AUROC_J(rest) = the same on all patches by writers other than W.
- Self drop for J: AUROC_J(rest) − AUROC_J(W).
- Baseline drop for W: mean over outside judges K of AUROC_K(rest_K) − AUROC_K(W), where outside judges exclude J
  and any judge of the same family as W (families: gpt-oss = {gpt-oss-20b, gpt-oss-120b}; GLM = {glm-4.7-flash,
  glm-4.5}; Qwen = {qwen3.5-9b, qwen3-coder}; Gemma, Kimi, Llama single). For K, rest_K excludes W and K's own
  writer, if any.
- **Primary: pooled self-judging gap** = mean over the 5 new self pairs of (self drop − baseline drop), 95% interval
  from 2,000 bootstrap resamples of issues (the same resampled issues for all pairs).
- Secondary, per self pair (descriptive; about 40–50 patches each, low power): self drop, baseline drop and their
  difference with intervals; leniency on failing patches = J's score minus the outside judges' mean, on W's failing
  patches vs other writers' failing patches; share of W's failing patches J scores ≥95 vs other writers' failing
  patches.
- Secondary, descriptive: the same pooled gap including Gemma (6 pairs).

## Reading rule (fixed now)

- Replicates: pooled gap > 0 and its interval excludes 0.
- Does not replicate: interval includes 0. Then the Gemma result is reported as one model's result, not a general
  effect.
- Opposite: interval entirely below 0.
- A per-model result is not called a finding on its own.

## Not tested here

Whether the cause is recognition of own patches or shared mistakes; patch length or harness style (all five new
writers used the same harness, mini-SWE-agent, so harness is constant within the new pairs); the critique-vs-score
text measure (kept for later, needs a defined classifier).

## Outputs

`derived/selfpref_<tag>.jsonl` per new judge; summary `derived/self_judging_replication_<date>.json`; W&B group
`self-judging-replication`; run log in that day's changelog.

## Result (added 2026-10-05, after the run)

Pooled self-judging gap over the five new self pairs: −0.036 [−0.089, 0.016]. By the reading rule above: **does not
replicate**; the Gemma result is reported as one model's result. Per pair (gap [95%]): Qwen3-Coder −0.032 [−0.241,
0.189]; gpt-oss-120b −0.046 [−0.133, 0.049]; GLM-4.5 −0.047 [−0.174, 0.116]; Kimi-K2 −0.036 [−0.113, 0.036];
Llama-4-Maverick −0.019 [−0.133, 0.101]; Gemma 4 31B (not counted) +0.135 [0.060, 0.210]. 333 patches rated by all nine
judges (55 left out); 26–35 own patches per new pair. Deviations from the procedure: failed calls (local DNS errors,
never sent) were retried with the same settings; the leniency measure uses, per patch, outside judges that exclude
the family of that patch's writer. Details: `changelog/2026-10-05.md`, "Run log: self-judging replication finished".
