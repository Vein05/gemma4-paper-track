# Spec: Gemma 4's own-patch check on SWE-bench Multilingual

DRAFT 2026-10-23. The setup and the smoke test (last section) run under this draft with the user's OK of 2026-10-23.
The full run and its judging need a second OK, and the sections they use are frozen first. Terms follow
`GLOSSARY.md`.

## Why

Every result in the paper comes from Python issues in SWE-bench Verified. The competition's Quality criterion asks how
well the work carries over to other problems. This run asks whether Gemma 4 31B rubber-stamps its own failing patches
in nine other languages, and whether the two fixes from Section 3.2 (breaking Gemma's ties by fewer model calls, and
GLM-4.5's score) still pick better patches there. Both fixes are fixed now from the Verified results, before any
Multilingual score exists.

## Issues

- SWE-bench Multilingual (`SWE-bench/SWE-bench_Multilingual`, revision `846e647b9f33c0b51b739d005d13d85493c9af09`,
  MIT): 300 issues from 41 repositories in 9 languages. The file is kept at
  `data/public/swe-bench-multilingual/data/test-00000-of-00001.parquet`.
- Language per repository: `scripts/multilingual_issues.py`, `LANGUAGE`. The counts per language match the dataset
  card (Ruby 44, Rust 43, PHP 43, Java 43, Go 42, C 30, JavaScript 26, TypeScript 17, C++ 12).
- An issue is kept only if its reference patch passes in our environment, as on Verified.

## Gemma's patches

- Agent: mini-SWE-agent 2.0.0 with its own SWE-bench runner (`minisweagent.run.benchmarks.swebench`), tool calling
  with its `bash` tool, step limit 250, one attempt per issue. This is the harness of the four public runs below.
- Prompts and settings: the public runs' saved config, copied from GLM-5's run
  (`data/public/swe-bench-multilingual/control_config.json`). Its system and instance prompts equal PyPI 2.0.0's
  `swebench.yaml`. Its observation and tool-error templates, command timeout (60 s), environment variables and shell
  (`bash -lc`) are used as saved. The cost limit ($3) never binds for a local model.
- Model: `google/gemma-4-31B-it-qat-w4a16-ct` revision `52f3f65b` served by vLLM 0.30.0 on the lab A100 (MCSR used
  0.31.0), with `--enable-auto-tool-choice --tool-call-parser gemma4 --reasoning-parser gemma4
  --enable-prefix-caching`. Temperature 0 and thinking off, as in the Verified runs. Two agents run at a time: with
  five, the agents' histories did not fit in vLLM's prefix cache (197,101 tokens) and were recomputed on most calls
  (0 of 64,144 looked-up tokens found in one 2-minute window; smoke test, 2026-10-23).
- Today's images source a conda script they do not contain from `/root/.bashrc`, so under `bash -lc` every command
  output starts with "No such file or directory". The public runs' outputs never show this line. The runner drops
  such `source` lines from each sandbox's `/root/.bashrc`. Smoke test, 2026-10-23: with the line and thinking off,
  Gemma ran the same `find` command 245 times on apache__druid-14136 and hit the step limit; without it, it submitted
  a patch after 50 calls.
- Container: a writable Apptainer 1.5.4 sandbox of the same Docker Hub image the public runs used
  (`docker.io/swebench/sweb.eval.x86_64.<id>:latest`), run with `--fakeroot --ignore-subuid --contain --cleanenv
  --no-home`, for the agent and for grading. Smoke test, 2026-10-23: without `--no-home`, `--contain` hides the image's
  `/root`, which holds Maven's downloaded dependencies (`/root/.m2`) and Go's module cache (`/root/go`); Docker shows
  it. Sandboxes are made writable before deletion, because Go's module cache is read-only. The saved shell `bash -lc`
  resets PATH through `/etc/profile`, so `cargo` is not on PATH in the Rust images. The public runs show the same
  ("cargo: command not found" in GLM-5's and DeepSeek-V3.2's tokio-rs__axum-2096 runs), so `bash -lc` is kept.
- Runner: `scripts/run_gemma_multilingual.py`, with litellm pinned to 1.104.0, the version of the Verified runs.
  litellm 1.106.2 imports its MCP proxy code for every request with tools and fails without the `mcp` package
  (smoke test, 2026-10-23).

## Other writers' patches (controls)

The four open-weight mini-SWE-agent 2.0.0 entries in `SWE-bench/experiments`, `evaluation/multilingual/`:
`20260213_mini-v2.0.0a0_glm-5`, `20260213_mini-v2.0.0a0_kimi-k2-5`, `20260213_mini-v2.0.0a0_deepseek-3-2`,
`20260216_mini-v2.0.0a0_minimax-2-5`. Patches and test reports come from the public `swe-bench-submissions` bucket
(`multilingual/<entry>/logs/<id>/`), and the model-call counts from each entry's `per_instance_details.json`
(`scripts/multilingual_issues.py controls`). Their official labels are used.

## Labels

`scripts/eval_apptainer.py` with swebench 4.1.0's test specs and grading, as on Verified. Checks: the reference patch
of every issue, and the regrading of 18 control patches against their official labels (half passing, round-robin over
repositories, as in the Verified check).

## Judges (budget about $5–6)

- Five judges: Gemma 4 31B, GLM-4.5, Qwen3.5-9B, gpt-oss-20b and Llama-4-Maverick. Kimi-K2 is left out because it
  cost 45% of the nine-judge total on Verified. Outside judges are the four judges other than Gemma.
- Prompt, settings, parser and the 8,000-token re-ask as in the held-out run (`scripts/fresh_judging.py`), in
  `scripts/multilingual_judging.py`.
- One OpenRouter provider per judge, no fallback, full precision where offered (2026-10-23). The held-out run let
  OpenRouter choose and spread most judges over several providers, and Venice, which served most of Qwen3.5-9B's
  held-out calls, no longer serves it. Gemma 4 31B: Novita (bf16). GLM-4.5: Z.AI (fp8, its only endpoint).
  Qwen3.5-9B: DeepInfra (bf16). gpt-oss-20b: DeepInfra (bf16). Llama-4-Maverick: Parasail (fp8, Meta's FP8 release).
- Patches judged: all of Gemma's patches and the control patches that fail (about 400). Control patches that pass are
  not judged, so this run has no self-judging gap.
- Test files are removed from every patch before judging, with the Verified pattern extended to the nine languages:
  `tests?/`, `testing/`, `spec/`, `__tests__/` and `testdata/` folders, and files named `test_*.py`, `*_test.py`,
  `*_test.go`, `*.test.[jt]s(x)`, `*.spec.[jt]s(x)`, `*_spec.rb`, `*Test.java`, `*Tests.java` and `conftest.py`.
- Cost estimate at the Verified prices per call: $0.0030 per patch for the five judges, so about $2.1 for about 700
  patches, and up to about $4.3 if Multilingual prompts are twice as long.

## Measures and reading rules (fixed before any Multilingual score)

95% intervals from 2,000 bootstrap resamples of issues.

1. Rubber-stamp rate: share of Gemma's own failing patches it scores 100, beside the share of control failing
   patches it scores 100.
2. Leniency on own failing patches minus leniency on control failing patches, with the four outside judges. The
   rubber-stamping replicates if the lower bound is above 0.
3. Choosing patches to submit, on Gemma's own patches: the share passing in the top quarter and the top half by
   (a) Gemma's score, (b) Gemma's score with ties broken by fewer model calls, (c) GLM-4.5's score and (d) the mean of
   Gemma's and Qwen3.5-9B's ranks. A fix carries over if its gain over (a) has a lower bound above 0.
4. Descriptive only: the rubber-stamp rate and leniency per language.

## Smoke test

- Issues: one per language (9). Within each language, `random.Random(0).choice` over the sorted issue ids
  (`scripts/multilingual_issues.py issues`, key `smoke`).
- Steps:
  1. Reference patches of the 9 issues graded in our environment. All should pass.
  2. Toolchain check in each of the 9 sandboxes: `which` of the language tools with `bash -c` and `bash -lc`, with
     and without `--no-home`.
  3. 18 control patches regraded against their official labels.
  4. Gemma's agent runs on the 9 issues with the full config. Checks: tool calls parse, patches are non-empty, the
     model-call count is saved, and the time per issue on the shared A100.
  5. The 9 Gemma patches and 9 control failing patches judged by the five judges (under $0.10). This checks prompt
     length and cost.
- The full run starts only after the user's OK.

## Full run (started 2026-10-23, 23:18 UTC, with the user's OK)

- Gemma's agents on all 300 issues in the fixed order, 2 at a time, then the vLLM server is stopped, then the patches
  are graded on the CPUs (`scripts/lab/run_multilingual_full.sh`, output `runs/ml-main/` on the server).
- At the same time, the reference patches of all 300 issues are graded on the CPUs (`scripts/lab/gold_multilingual.sh`,
  `runs/ml-gold/`).
- Steps 4 and 5 of the smoke test were not finished: with five agents the runs were too slow (above). The first issues
  of the full run are checked in their place before the run is left alone.
- Judging needs the Judges and Measures sections frozen first.
