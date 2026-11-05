# Gemma 4 31B-it agent attempts on SWE-bench Verified Mini (third-party runs)

Normalized table of patches and official SWE-bench pass/fail labels from six public Hugging Face
datasets by user `n-pelleriti` (AlphaDiana project). These are third-party runs: we did not run them,
and everything below is what the datasets and their logs state. Built 2026-10-05 by
`scripts/gemma_own_attempts.py`; `attempts.jsonl` is its output, `summary.json` has the counts.

The public repository's copy of `attempts.jsonl` has no `patch` field, because these datasets declare no license.
Running the script restores it.

Task set: SWE-bench Verified Mini (`MariusHobbhahn/swe-bench-verified-mini`), 50 tasks,
25 `django/django` + 25 `sphinx-doc/sphinx`. All six datasets use the same 50 instance ids.
Model: `google/gemma-4-31B-it`.

## Source datasets (HF commit sha at extraction time)

| dataset (`n-pelleriti/...`) | sha | run(s) | harness |
|---|---|---|---|
| alphadiana-sweagent-gemma4-directllm-20260727 | cb3478d1c7d2e86b6cbe21462dbf043195937496 | `20260724-...-directllm-gemma-4-31b-it-sweagent-v02` (50 tasks); `20260727T103555Z-...-podman-smoke` (1 task) | sweagent (official SWE-agent run-batch, default config, "DirectLLM baseline") |
| alphadiana-swe-mini-opencode-gemma4-20260602-818023 | bc170437a93ff50f1912a00141c990d438e562c5 | `20260602-...-opencode-gemma-4-31b-it-full-818023` | opencode 1.3.2 |
| alphadiana-swe-mini-opencode-gemma4-20260725-v04 | e64402afa90a6047909ded9ed9acda1502390f93 | `20260725-...-opencode-gemma-4-31b-it-v04-proxyphase-mt131072` | opencode |
| alphadiana-swe-mini-openclaw-gemma4-20260724-k9q7 | c52c3361ecd4305c1f10a40109c116914965ebce | `20260724-...-openclaw-gemma-4-31b-it-v02` | openclaw 2026.3.20 |
| alphadiana-swe-mini-zeroclaw-gemma4-20260724-r6m2 | e903a16f1fc685fb2e7d3b90f591826a579bd9c5 | `20260724-...-zeroclaw-gemma-4-31b-it-v02` | zeroclaw 0.6.9 |
| alphadiana-swe-mini-direct-gemma4-20260725-m8v4 | 29ad528cf43a17438ed231a726f58d022a853ac2 | `20260724-...-direct-noharness-gemma-4-31b-it-h200-v01` | direct_noharness (one-shot LLM call, no agent loop) |

Full run names are in `attempts.jsonl` (`run` field). One sample per task per run (`num_samples=1`).

## Extraction

Row schema: `dataset, run, instance_id, harness, patch, resolved, status, label_source, patch_source`,
plus `status_detail` and `usable` (= non-empty patch AND `status == valid_scored` with an evaluator
`resolved` label). `label_source` and `patch_source` are paths inside the dataset.

- sweagent: patch = `model_patch` in `sweagent_results/<run>/preds.json` (matches the per-instance
  `.pred` files). Label = `official_reports/<run>.<run>.json` (`resolved_ids` -> true,
  `unresolved_ids` -> false; `error_ids` -> `eval_error`; `empty_patch_ids` -> `empty_patch`).
- All other datasets: the run JSONL `results/<run>.jsonl` has one row per task (identical to
  `results/<run>/tasks/swe_<iid>.json`). Patch = `.../swebench_eval/<iid>/patch.diff` (the exact
  patch given to the evaluator; equals the JSONL `predicted` field in every case). Label =
  `.../swebench_eval/<iid>/report.json` `resolved` (SWE-bench per-instance report). The script asserts
  it equals the JSONL `correct`/`score_metadata.resolved`; no disagreements.
- Rows with a non-empty patch but no `report.json` (evaluator never produced a report) get
  `status=eval_error`, `resolved=null`. In all 53 such non-sweagent cases `run_instance.log` shows
  `git apply` failed (`status_detail=patch_apply_failed`). Official SWE-bench
  treats these as errors, not resolved. The sources themselves label them `valid_scored` with
  `correct=false`; we do not use that as an official label.
- `empty_patch` rows have `resolved=false` (as scored by the source) but are not usable.
- `provider_error` / `runtime_error`: `resolved=null`. A patch is kept if one exists (direct run,
  `sphinx-doc__sphinx-11510`: patch generated, evaluator image build failed) but the row is not usable.

## Counts per run

| run | harness | tasks | usable | resolved (of usable) | other statuses |
|---|---|---|---|---|---|
| sweagent v02 | sweagent | 50 | 34 | 23 | 14 empty_patch, 2 eval_error (evaluator test timeout, 1800 s) |
| sweagent podman-smoke | sweagent | 1 (django-11880) | 1 | 1 | |
| opencode 818023 | opencode | 50 | 32 | 19 | 14 provider_error (context overflow), 1 runtime_error (image build), 3 empty_patch |
| opencode v04 | opencode | 50 | 47 | 18 | 1 runtime_error, 1 empty_patch, 1 eval_error (patch_apply_failed) |
| openclaw v02 | openclaw | 50 | 48 | 22 | 1 runtime_error, 1 eval_error (patch_apply_failed) |
| zeroclaw v02 | zeroclaw | 50 | 43 | 22 | 4 runtime_error, 3 eval_error (patch_apply_failed) |
| direct no-harness | direct_noharness | 50 | 1 | 0 | 48 eval_error (patch_apply_failed), 1 runtime_error (image build) |

Total 301 rows, 206 usable, 105 resolved (205 / 104 without the 1-task smoke run).

## Cross-check against dataset READMEs

All match.

- sweagent v02: README 23/50 resolved, 14 empty patches, 2 evaluator errors; official report
  and our table agree (34 completed = 23 resolved + 11 unresolved).
- opencode 818023: README 35 valid_scored (19 correct), 14 provider_error, 1 runtime_error. Ours: 19 resolved
  of 32 evaluated; the other 3 of the README's "35 valid_scored" have an empty patch (README counts them
  as valid_scored with correct=false; we mark them `empty_patch`).
- opencode v04: README 49 valid_scored, 18 correct. Ours: 18 resolved; of the 49, 1 empty patch and 1
  patch-apply failure are not usable.
- openclaw: 49 valid, 22 correct. Ours: 22 resolved; 1 patch-apply failure.
- zeroclaw: 46 valid, 22 correct. Ours: 22 resolved; 3 patch-apply failures.
- direct: 49 valid, 0 correct. Ours: 0 resolved; only 1 of the 49 was actually evaluated, the rest
  failed `git apply`.

## Odd things / caveats

- README "valid_scored" includes rows where the evaluator never ran (empty patch or patch did not apply).
  "Valid-only accuracy" in the READMEs is therefore not an accuracy over evaluated patches.
- The direct no-harness run is almost entirely unusable (48/50 patches do not apply; 9 hit the length
  limit per its README). It contributes one usable attempt (fail). The sweagent dataset README says an
  "invalid AlphaDiana `direct-noharness` one-shot run" is deliberately not included there; this direct run
  (0/50, almost all patches malformed) is probably that run, but the datasets do not say so.
- The sweagent smoke run is a 1-task "runbook qualification" run on `django__django-11880`, with a
  different run protocol (revision-pinned vLLM args). It is included as its own run; the cross-run
  figures in `summary.json` are given with and without it (same pass/fail-instance result).
- The sweagent evaluator errors (sphinx-7985, sphinx-8269) were evaluator timeouts, not patch-apply failures.
- Runs are not independent of config: the opencode 818023 run used different vLLM sampling than the
  others (see below), and harnesses differ in prompts and tools.
- Across the usable rows, some patches are byte-identical across runs; `summary.json` counts unique
  patches per instance. No identical patch carries conflicting labels.

## Precision, serving, decoding

The dataset READMEs state none of this. From the included vLLM logs and run configs (not README):

- Serving: vLLM 0.19.1 (`Gemma4ForConditionalGeneration`), `dtype=torch.bfloat16`, no quantization,
  `max_model_len=262144`, `tool_call_parser=gemma4`, `reasoning_parser=gemma4`. Model revision
  `842da3794eaa0b77d5f08bae87a17459d91ff475` is pinned in the sweagent dataset's
  `metadata/locked-revisions.env` (other datasets show `revision=None`).
- Tensor parallel: 4 GPUs for opencode 818023; 2 GPUs for all others.
- opencode 818023: no generation-config override. vLLM log: model `generation_config.json` defaults
  applied (`temperature=1.0, top_k=64, top_p=0.95`); no `enable_thinking` chat-template kwarg in the vLLM args.
- opencode v04, openclaw, zeroclaw, direct (and sweagent): `generation_config=vllm`,
  `override_generation_config={'presence_penalty': 1.5}`, `default_chat_template_kwargs={'enable_thinking': True}`,
  prefix caching on.
- sweagent run config (per-instance `.config.yaml`): `temperature=0.0`, `top_p=0.95`,
  `per_instance_call_limit=80`, `max_output_tokens=131072`. `MAX_TOKENS=131072` in job metadata.
  The opencode v04 run name ends `mt131072` (likely the same max-tokens setting; not verified).
- Per-request sampling for opencode/openclaw/zeroclaw/direct was not checked beyond the server settings above;
  the JSONL rows have no temperature field.

## Rerun

```
python scripts/gemma_own_attempts.py --cache <dir>   # downloads small files only, pinned to the shas above
```
