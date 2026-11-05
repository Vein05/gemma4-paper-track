# Spec: is Gemma still lenient on its held-out patches once the leftover added files are removed?

Written 2026-11-03, before any stripped patch was scored. Proposed in `notes/committee-2026-11-03/fable_story.md` (D3);
approved by the user ("sure do it").

## Why

142 of Gemma's 180 held-out patches add a file (mostly reproduction scripts and small test projects); on SWE-bench Lite
none of Gemma's 295 patches do. A judge sees those files in the diff. Gemma may trust a patch because it sees a test
script it wrote, or the outside judges may distrust patches with leftover files. Either would change the paper's
held-out leniency (+16.6) for a reason other than the code change.

## Stripping rule (fixed before scoring)

For every held-out patch, by every writer (the 957 patches of the paper's held-out analysis): remove each added-file
block (`new file mode`) unless both hold:

- its first path component is the first path component of a file that some patch on the same repository modifies
  (an existing package folder such as `django/`, `sklearn/`, `lib/`), and
- it is not a backup (`.bak`, `.orig`, `.tmp`, `.backup`, `.rej`).

So `reproduce_issue.py`, `repro/models.py` and `test.png` are removed; `sklearn/utils/_isfinite.py` is kept. Labels are
the original patches' labels: the removed files are outside the package and are not run by the hidden tests. A patch
left empty is dropped and counted.

## Judging

All nine judges of the paper's held-out analysis (Gemma 4 31B hosted, gpt-oss-20b, Qwen3.5-9B, GLM-4.7-Flash,
Qwen3-Coder, gpt-oss-120b, GLM-4.5, Kimi-K2, Llama-4-Maverick), OpenRouter, same prompt, settings, parser and re-ask
as `scripts/fresh_judging.py` (providers not pinned, as in the original run). Every stripped patch is scored, including
patches the rule did not change, so the comparison is within one fresh run and the unchanged patches give the run-to-run
noise. Script `scripts/stripped_rescore.py`; rows `scripts/derived/stripped_<judge>.jsonl`. Cost estimate: about $9.

## Measures

The paper's leniency (Gemma's score minus the outside panel's mean on the same patch, own failing minus other writers'
failing, judges of the writer's family dropped from the panel; 2,000 issue resamples, seed 0):

1. **Primary:** leniency on the stripped patches.
2. Leniency on the original patches over the same patch set (from the paper's rows), and the paired difference
   original minus stripped.
3. Run-to-run noise: on patches the rule did not change, the mean absolute difference between the original and new
   score per judge.
4. Description: Gemma's mean score and the panel's mean score on Gemma's changed patches, before and after stripping.

## Reading, fixed now

- **Confound closed:** stripped leniency at least +8 with the interval above 0. The paper adds one sentence in
  Limitations and reports the number in the supplement.
- **Leftover files explain part of it:** otherwise. The paper says part of the held-out leniency comes from leftover
  files in the diff and leans on SWE-bench Lite (+17.8, no added files) for the main claim.

## Logging

Changelog entry; W&B group `stripped-files`; analysis `scripts/derived/stripped_files_rescore_2026-11-03.json`.
