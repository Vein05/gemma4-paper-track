# Spec: why does post-training make Gemma lenient? Familiarity test and a second model family

Written 2026-11-02, before any score from these runs was computed. Approved by the user the same day (chat: "let's run
them"). Exploratory follow-up to `spec/base-vs-instruct.md`; not part of the paper's frozen plans. The user asked that
not everything go into the Writeup: these results may end up in a supplement or nowhere.

## Starting point

`spec/base-vs-instruct.md` (result in `scripts/derived/base_vs_instruct_2026-11-02.json`): on the same plain-text prompt,
the pretrained Gemma 4 31B ranks Gemma's own failing patches no higher than other writers' failing patches on the same
issue (leniency +0.2 [−4.2, +4.7] percentile points); the instruction-tuned model does (+10.0 [+6.3, +13.6]); the
difference is +9.8 [+5.4, +13.8]. The published comparison closest to this (Chen et al., EMNLP 2025, "Beyond the
Surface: Measuring Self-Preference in LLM Judgments"; AlpacaEval chat answers, Llama and Qwen) found that post-training
did not increase self-preference.

Two explanations remain, and two tests address them.

## Test 1: does familiarity explain the shift? (Gemma, no new models)

The instruction-tuned model wrote the "own" patches. It may favour text that reads like its own writing. If that is
the mechanism, then among patches it did not write, the ones that post-training made more familiar should also have
had their scores raised more.

Runs: the pretrained and the bf16 instruction-tuned Gemma 4 31B read the same 957 plain-text prompts again
(`data/judge-prompts/base_vs_instruct_plain.jsonl`). From one forward pass per patch, `probe_extract.py fam` records
log P("100") after `SCORE: ` (a check against the earlier run) and the summed log-likelihood of the scored patch's
tokens (the text inside the last `<patch>` block), each token conditioned on everything before it.

Measures, per patch:

- Familiarity F(model) = patch log-likelihood divided by the number of patch tokens.
- Familiarity gain G = F(instruction-tuned) − F(pretrained).
- Score shift S = percentile of log P("100") under the instruction-tuned model minus that under the pretrained model,
  both from the existing `plain.jsonl` files (percentiles among the 957, as in `spec/base-vs-instruct.md`).

Primary: among other writers' failing patches only, the within-issue correlation of G and S. G and S are turned into
ranks over that set, ranks are centred within each issue (issues with at least two such patches), and the Pearson
correlation of the centred ranks is taken. 95% interval from 2,000 resamples of issues, seed 0.

Secondary (all failing patches, own and other writers', issues with at least one own failing patch and one other):
within-issue regression of S on an own-patch indicator alone (coefficient b0, which is the leniency difference in
this model pair) and on the indicator plus the rank of G (coefficient b1). Share explained = 1 − b1/b0, with a
bootstrap interval.

Descriptive: median G for own failing and for other writers' failing patches; overlap = share of own failing patches
whose G lies between the 10th and 90th percentile of other writers' failing patches' G.

Reading, fixed now:

- **Familiarity explains it:** primary interval above 0 and the upper end of b1/b0's interval below 0.5.
- **Familiarity contributes:** primary interval above 0, otherwise.
- **No sign of familiarity:** primary interval includes 0 (or is below 0) and the lower end of b1/b0's interval is
  above 0.5.
- Any other pattern is inconclusive.
- If the overlap is below 20%, own and other patches barely share familiarity values; the secondary result is then
  reported as unreliable, and only the primary is used.

Correctness check: log P("100") from this run must match the earlier run (Pearson above 0.999 per model). The first
row checks that the hidden state taken from the final norm reproduces the model's own logits (largest difference
below 0.5).

## Test 2: a second model family (OLMo 3 32B, base and instruction-tuned)

Does post-training in general make a judge favour Gemma's failing patches, or only Gemma's own post-training? Run the
same plain-text comparison with a pretrained/instruction-tuned pair from a family that wrote none of the patches.
Writers are Gemma, Llama 4 Maverick, GLM-4.5, gpt-oss-120b, Qwen3-Coder and Kimi-K2, which rules out those families.

Models (bf16, ungated): `allenai/Olmo-3-1125-32B` (pretrained) and `allenai/Olmo-3.1-32B-Instruct`. The model cards
list the chain pretrained → `Olmo-3.1-32B-Instruct-SFT` → `-DPO` → `-Instruct`. 32.2B parameters, 65,536-token context.
Downloaded 2026-11-02 to `<workdir>/gemma4-paper-track/models/olmo-3-32B` and `.../olmo-3.1-32B-Instruct`.

Prompt: the identical 957 plain-text prompts, no chat template. OLMo has no beginning-of-sequence token, so none is
added. Its tokenizer joins the space to the next token, so the score is read as log P(" 100") after `SCORE:` (the
`fam` mode moves the space automatically; `space_moved` is recorded).

Pilot (format only): the 40 pilot prompts. Pass: median probability that the next token starts with a digit is at
least 0.5 for both OLMo models. If either fails, stop and report; no prompt change without a new addendum.

Measures: as in `spec/base-vs-instruct.md` (leniency L, D = L(instruction-tuned) − L(pretrained), AUROCs), plus the
difference D(Gemma) − D(OLMo) with both pairs resampled over the same issues.

Reading, fixed now:

- **Post-training in general:** D(OLMo)'s interval above 0 and the interval of D(Gemma) − D(OLMo) includes 0.
- **Both, Gemma's larger:** D(OLMo)'s interval above 0 and the interval of D(Gemma) − D(OLMo) above 0.
- **Specific to Gemma's post-training:** D(OLMo)'s interval includes 0 or is below 0, and the interval of
  D(Gemma) − D(OLMo) is above 0.
- Any other pattern is inconclusive.

The OLMo familiarity gain on Gemma's patches (same measure as Test 1) is reported as description only.

Not run unless the user asks: the OLMo SFT and DPO checkpoints, which would split post-training into stages.

## Cost and logging

About 130 GB of downloads. Scoring: about 30 minutes per model per run on the A100, four runs (two Gemma, two OLMo).
No API spend. Analysis: `scripts/post_training_followup.py`. W&B group `base-vs-instruct`. Changelog entry in
`changelog/2026-11-02.md`.
