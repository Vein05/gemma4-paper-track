# Data

This file describes the project's full `data/` folder. Folders missing from the public repository are either raw
runs, which are on [Hugging Face](https://huggingface.co/datasets/vein05/gemma4-paper-track-data), or public downloads
whose source is listed below.

- `public/nebius-swe-agent-trajectories/`: datasets-server JSON pages of the public Hugging Face dataset
  `nebius/SWE-agent-trajectories`, rows 0–3,999 in pages of 100 (`rows_<offset>.json`; `rows_3400.json` failed to
  download and is unreadable, so 3,900 rows load). Downloaded 2026-10-04. Used by `scripts/api_quickcheck.py`, `scripts/selfjudge_matrix.py`,
  `scripts/selection_test.py` (pass `--cache data/public/nebius-swe-agent-trajectories`). Public data only.
- Competition data is never stored here.
- `public/swe-bench-live/`: SWE-bench-Live lite submissions (13 `<name>__preds.json` + `<name>__results.json` from
  `github.com/SWE-bench-Live/submission` at commit `cba8a6d3`; no license file in that repo) and `lite.parquet`
  (`SWE-bench-Live/SWE-bench-Live`, lite split, revision `b51a8642`, MIT). Downloaded 2026-10-05. Used by
  `scripts/live_data.py` (`spec/post-cutoff-test.md`).
- `public/swe-bench-multilingual/` (added 2026-10-23, `spec/multilingual-replication.md`): `data/test-00000-of-00001.parquet`,
  the SWE-bench Multilingual test split (`SWE-bench/SWE-bench_Multilingual`, revision `846e647b`, MIT, 300 issues;
  sha256 `92abca7c…`); `issues.json`, language per issue, the 9 smoke-test issues and a fixed random order (seed 0);
  `attempts.jsonl`, patches, official labels and model-call counts of the four open-weight mini-SWE-agent 2.0.0 entries
  (GLM-5, Kimi-K2.5, DeepSeek-V3.2, MiniMax-M2.5) from the public `swe-bench-submissions` bucket
  (`multilingual/<entry>/logs/<id>/`; where `patch.diff` is missing, the submission saved in the run's trajectory,
  which equals it on 12 of 12 checked) and `SWE-bench/experiments` (`per_instance_details.json`);
  `control_config.json`, the mini-SWE-agent config saved in GLM-5's run. All from `scripts/multilingual_issues.py`.
- `public/gemma4-own-attempts/`: Gemma 4 31B-it agent attempts on SWE-bench Verified Mini from six third-party HF
  datasets (`n-pelleriti/alphadiana-*`), normalized by `scripts/gemma_own_attempts.py`; own README with shas.
  The public repository's `attempts.jsonl` has no patch text (these datasets declare no license). Ids, labels and
  sources stay. Rebuild it with `scripts/gemma_own_attempts.py` before rerunning `scripts/self_preference.py` or
  `scripts/selection_test.py`, which read the patches.
  `swe-bench-verified-mini.parquet` from `MariusHobbhahn/swe-bench-verified-mini` (sha `b316c349`).
- `public/swe-bench-verified-mini-control/attempts.jsonl`: patches and SWE-bench reports of six mini-SWE-agent
  submissions on the same 50 issues (`SWE-bench/experiments` entries; files from the public
  `swe-bench-submissions` S3 bucket, `bash-only/<entry>/logs/<issue>/patch.diff` and `report.json`), downloaded
  2026-10-05; labels agree with each entry's `per_instance_details.json`.
- `public/swe-bench-verified-control-fresh/`: `attempts.jsonl`, patches and SWE-bench reports of the five
  mini-SWE-agent control entries (first five in the list below) on SWE-bench Verified issues outside the Mini issues,
  from the same S3 bucket, downloaded 2026-10-05 by `scripts/fresh_issues.py`; `sample.json`, the fixed random order of
  the held-out issues (seed 0) and the pilot issues; `mini50_ids.json`, the Mini issue ids.
- `mcsr-runs/` (added 2026-10-06): Gemma 4 31B (`gemma-4-31B-it-qat-w4a16-ct`, revision `52f3f65b`) in
  mini-SWE-agent 1.7.0 on MCSR Magnolia. One folder per job: `main-a`, `main-b` (the 200
  held-out issues, positions 0–99 and 100–199 of `sample.json`), `mini50` (the Mini issues), `pilot`, `smoke`;
  `gold`, `gold-retry`, `gold-redo` (reference patches graded on Magnolia), `validate`, `regrade` (grading checks).
  Each holds `preds.jsonl`, `labels.jsonl`, `run.json`, `trajs/` and logs. Files named `*.before-*.jsonl` are the
  copies kept before a re-grade or a second run of one issue. The release copies these with
  the cluster account name removed (`make_release.sh`).
- `hand-codes/` (added 2026-10-22): the 31 held-out cases where Gemma scored its own failing patch 100 and at least
  two outside judges scored it 50 or less. `rubber-stamp-cases.md` is the coding sheet (patch, the low-scoring outside
  judges' answers, Gemma's answer, codebook), built by `scripts/rubber_stamp_reasons.py packet`.
  `rubber-stamp-coder-a.csv` and `rubber-stamp-coder-b.csv` hold two independent codings by Claude agents (Sonnet,
  then Opus without access to the first), `rubber-stamp-coder-b-notes.md` the second coder's reasons;
  `rubber_stamp_reasons.py agree` compares them.

## Revisions and licenses (checked 2026-10-05)

Hugging Face commit shas from `huggingface.co/api/datasets/<name>`; GitHub shas from the GitHub API. "None declared"
means the dataset card has no license field.

| Source | Revision | License | Used by |
|---|---|---|---|
| `MariusHobbhahn/swe-bench-verified-mini` | `b316c349947c29963fce3f4a65967c9807a4b673` | none declared | issue set of the main study |
| `n-pelleriti/alphadiana-*` (six Gemma 4 datasets) | shas in `public/gemma4-own-attempts/README.md`; unchanged on 2026-10-05 | none declared | Gemma patches of the main study |
| `n-pelleriti/alphadiana-sweagent-qwen35-directllm-20260728` | `b696dd1d4ba89d19566126baa7600b8821c08036` | none declared | `scripts/retry_loops.py` (not stored here) |
| `n-pelleriti/alphadiana-swe-mini-qwen35-27b-20260729` | `8493c18fdeaf7b3005df4175ad64a99b2e0bd286` | none declared | `scripts/retry_loops.py` (not stored here) |
| `rishaviitd/kaggle.gemma.coding.agent` (GitHub) | HEAD on 2026-10-05: `8ed7dec72992e2e62098c6913102080f09fa8824` (committed 2026-10-05 15:34 UTC; the clone used earlier that day may be older) | not checked | `scripts/retry_loops.py` (not stored here) |
| `nebius/SWE-agent-trajectories` | `68195a1450865274106246d0d0296a1d6807b88e` (last modified 2024-12-23) | CC-BY-4.0 | earlier pointwise/pairwise probes; not in git (270 MB) |
| `SWE-bench/experiments` (GitHub) | HEAD on 2026-10-05: `40f164d5b8f1d249bf95a6df8b74b577fd8e519d` | not checked | control-entry names; patch files come from the unversioned `swe-bench-submissions` S3 bucket |
| `SWE-bench/SWE-bench_Multilingual` | `846e647b9f33c0b51b739d005d13d85493c9af09` (last modified 2026-08-17) | MIT | `spec/multilingual-replication.md` |
| SWE-bench-Live submission repo and lite split | `cba8a6d3` and `b51a8642` (above) | repo: no license file; lite split: MIT | `scripts/live_data.py`; not in git |

Control entries in `public/swe-bench-verified-mini-control/attempts.jsonl` (`writer` field), all from
`bash-only/` in the S3 bucket: `20250802_mini-v1.0.0_qwen3-coder-480b-a35b-instruct`, `20250807_mini-v1.7.0_gpt-oss-120b`,
`20250822_mini-v1.9.1_glm-4.5`, `20250807_mini-v1.7.0_kimi-k2-instruct`,
`20250720_mini-v0.0.0-Llama-4-Maverick-17B-Instruct`, `20251209_mini-v1.17.2_devstral-small-2512`. The first five
entries also hold patches for 495–499 of the 500 SWE-bench Verified issues (12 repositories), which the held-out
study uses as controls.

## Added 2026-11-01

- `public/third-party-lite/gemma/`: Gemma 4 31B's SWE-bench Lite run published by another team
  (`dougalldeepmind/2026-10-10-swebench-gemma4-lite-gemma-v2`, sha `1c5f3d3be50e4ca6ceb17654987fd34e6cf23f96`, no
  license declared): each issue's `preds.json`, `results/` (their grading: 166 of 300 resolved) and run metadata; not
  the transcripts. Downloaded by `scripts/lab/pull_third_party_lite.py`.
- `public/third-party-lite/patches.jsonl`: the 1,478 patches judged in `spec/third-party-lite.md` (Gemma's and four
  Lite leaderboard entries' from the public `swe-bench-submissions` bucket, test hunks removed), built by
  `scripts/third_party_lite.py build`.
- `public/livecodebench-submissions/`: released LiveCodeBench programs and grades of DeepSeek-V3, GPT-4o (2024-08-06),
  Claude 3.5 Sonnet (2024-10-22) and Qwen2.5-Coder-32B (`LiveCodeBench/submissions`, commit `6ca212e9`,
  `Scenario.codegeneration_10_0.2_eval_all.json` per model).
- `livecodebench-pilot/`: Gemma 4 31B's LiveCodeBench programs and grades from the lab A100 (`spec/livecodebench-pilot.md`),
  the 8,000-token rerun, the hand check (`hand-check/`) and the judged programs (`judging/programs.jsonl`,
  `spec/livecodebench-judging.md`).
- In the public repository (`make_release.sh`): `livecodebench-pilot/gemma4-31b.jsonl`, `gemma4-31b-8k.jsonl`, the two
  `summary_*.json` files and `hand-check/coding.csv`. `public/third-party-lite/patches.jsonl` and
  `livecodebench-pilot/judging/programs.jsonl` are there without third-party text: no Gemma patch text from the Lite
  run (no license declared), no Lite issue text and no LiveCodeBench problem statement (CC, version not given). Ids,
  writers and labels stay, which is all the analyses read; `scripts/lab/pull_third_party_lite.py` with
  `scripts/third_party_lite.py build`, and `scripts/lcb_judging.py build`, restore the text. Not there: the Lite run
  folder, `public/livecodebench-submissions/` (MIT, `LiveCodeBench/submissions`), the `*_eval_all.json` grades and
  `hand-check/packet.md`, which hold problem statements.
