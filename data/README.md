# Data

- `public/nebius-swe-agent-trajectories/`: datasets-server JSON pages of the public Hugging Face dataset
  `nebius/SWE-agent-trajectories`, rows 0–3,999 in pages of 100 (`rows_<offset>.json`; `rows_3400.json` failed to
  download and is unreadable, so 3,900 rows load). Copied 2026-10-05 from the session scratchpad where they were
  downloaded on 2026-10-04. Used by `scripts/api_quickcheck.py`, `scripts/selfjudge_matrix.py`,
  `scripts/selection_test.py` (pass `--cache data/public/nebius-swe-agent-trajectories`). Public data only.
- Competition data is never stored here; it stays on Kaggle and in the session scratchpad.
- `public/swe-bench-live/`: SWE-bench-Live lite submissions (13 `<name>__preds.json` + `<name>__results.json` from
  `github.com/SWE-bench-Live/submission` at commit `cba8a6d3`; no license file in that repo) and `lite.parquet`
  (`SWE-bench-Live/SWE-bench-Live`, lite split, revision `b51a8642`, MIT). Downloaded 2026-10-05. Used by
  `scripts/live_data.py` (`spec/post-cutoff-test.md`).
- `public/gemma4-own-attempts/`: Gemma 4 31B-it agent attempts on SWE-bench Verified Mini from six third-party HF
  datasets (`n-pelleriti/alphadiana-*`), normalized by `scripts/gemma_own_attempts.py`; own README with shas.
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
  mini-SWE-agent 1.7.0 on MCSR Magnolia, copied with `./ssh.sh get`. One folder per job: `main-a`, `main-b` (the 200
  held-out issues, positions 0–99 and 100–199 of `sample.json`), `mini50` (the Mini issues), `pilot`, `smoke`;
  `gold`, `gold-retry`, `gold-redo` (reference patches graded on Magnolia), `validate`, `regrade` (grading checks).
  Each holds `preds.jsonl`, `labels.jsonl`, `run.json`, `trajs/` and logs. Files named `*.before-*.jsonl` are the
  copies kept before a re-grade or a second run of one issue (`changelog/2026-10-06.md`). The release copies these with
  the cluster account name removed (`make_release.sh`).

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
| SWE-bench-Live submission repo and lite split | `cba8a6d3` and `b51a8642` (above) | repo: no license file; lite split: MIT | `scripts/live_data.py`; not in git |

Control entries in `public/swe-bench-verified-mini-control/attempts.jsonl` (`writer` field), all from
`bash-only/` in the S3 bucket: `20250802_mini-v1.0.0_qwen3-coder-480b-a35b-instruct`, `20250807_mini-v1.7.0_gpt-oss-120b`,
`20250822_mini-v1.9.1_glm-4.5`, `20250807_mini-v1.7.0_kimi-k2-instruct`,
`20250720_mini-v0.0.0-Llama-4-Maverick-17B-Instruct`, `20251209_mini-v1.17.2_devstral-small-2512`. The first five
entries also hold patches for 495–499 of the 500 SWE-bench Verified issues (12 repositories), which the fresh
replication in `todo.md` can use as controls.
