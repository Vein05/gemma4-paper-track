# Charter: does Gemma rubber-stamp its own patches in another team's run? (SWE-bench Lite)

Written 2026-11-01, with the user's OK ("go into the server, pull those traces, and then let's see ... if this is true
or not"). Terms follow `GLOSSARY.md`.

## Question

The paper's Gemma patches come from two sources. The Mini patches were published by the AlphaDiana project; the
held-out patches we generated ourselves on SWE-bench Verified with mini-SWE-agent. Both are SWE-bench Verified. Another
team has since published Gemma 4 31B's patches for all 300 SWE-bench Lite issues. We had no part in that run: they
chose the agent, the settings, the hardware and the grading. Does Gemma rubber-stamp its own failing patches there too?

## Data

- Gemma's patches: `dougalldeepmind/2026-10-10-swebench-gemma4-lite-gemma-v2` (Hugging Face, sha `1c5f3d3b`,
  last modified 2026-10-11, no license declared). `google/gemma-4-31B-it` at revision `842da379` (full weights, not
  the 4-bit checkpoint), thinking on, mini-SWE-agent 2.2.1, one attempt per issue. Their own grading: 300 of 300
  graded, 166 resolved, 134 not. We use their labels; the dataset states two limits (two `requests` issues resolve
  without a source fix, and a local HTTPBin server stands in for the public one).
- Other writers' patches on the same issues: four SWE-bench Lite leaderboard entries (`SWE-bench/experiments`,
  patches from the public `swe-bench-submissions` bucket, labels from each entry's `results/results.json`):
  `20250111_moatless_deepseek_v3`, `20250306_SWE-Fixer_Qwen2.5-7b-retriever_Qwen2.5-72b-editor`,
  `20250901_entroPO_R2E_QwenCoder30BA3B`, `20250526_sweagent_claude-4-sonnet-20250514`. Four teams, four harnesses,
  open and closed models, none of them Gemma.
- Issue text: `princeton-nlp/SWE-bench_Lite`, test split.
- Patches as in the paper: test-file hunks removed, at most 30,000 characters, empty patches left out.
- Overlap with the paper: 37 of the 300 issues are among the held-out issues and 7 among the Mini issues (different
  patches; reported, not removed).

## Judging and measures

The paper's nine judges, prompt, settings, parser and re-ask (one re-ask at 8,000 tokens), through OpenRouter from this
Mac (`scripts/third_party_lite.py`, built on `scripts/fresh_judging.py`). Gemma as judge is the hosted Gemma 4 31B, as
in the paper. Reported, with 95% intervals from 2,000 bootstrap resamples of issues:

1. Rubber-stamp rate: the share of Gemma's own failing patches that Gemma scores 100, against the share of other
   writers' failing patches it scores 100, and against what the outside judges give the same own failing patches.
2. Leniency: Gemma's score minus the outside judges' mean on the same patch, own failing patches minus other writers'
   failing patches; the same on passing patches.
3. Self-judging gap (AUROC), as in the paper.

The result holds if (1) Gemma scores a larger share of its own failing patches 100 than of other writers' failing
patches, and (2) the leniency difference on failing patches has a 95% interval above 0. It does not hold if the
interval of (2) includes 0. Either way it goes in the paper.

Cost: about 1,400 patches at $0.0067 per patch for nine judges, about $10 of OpenRouter credit. No GPU.

Change, 2026-11-01, before any score was read (the user: "we don't need to score every possible one ... see if we
can do it with the current money"): the credit was $4.23, so the judges are the seven that fit in it: Gemma and six
outside judges (gpt-oss-20b, gpt-oss-120b, Qwen3.5-9B, GLM-4.7-Flash, Qwen3-Coder, Llama 4 Maverick). GLM-4.5 and
Kimi-K2 are left out (about $6.6 together). Projected cost of the seven: about $2.2. The rule above is unchanged.

## How the paper would describe it, if it holds

Draft for `paper/writeup.md` (a new short subsection or one paragraph in Section 3; for the user to edit):

> **The effect holds in another team's run.** Every Gemma patch above came from runs on SWE-bench Verified. To check
> that the effect does not come from our setup, we used Gemma 4 31B's patches for the 300 issues of SWE-bench Lite
> released by another team (dougalldeepmind, 2026). We had no part in that run: they chose the agent
> (mini-SWE-agent 2.2.1), ran the full-precision model with thinking on, and graded the patches themselves. Gemma
> solved 166 of the 300 issues. We gave the 134 failing patches, and the patches of four leaderboard entries on the
> same issues, to the same nine judges. Gemma scored X% of its own failing patches 100, against Y% of the other
> writers' failing patches, and the outside judges scored the same own patches lower (leniency +Z [a, b]). The
> rubber stamp appears on a dataset, an agent and a grading setup that we did not choose.

If it does not hold, the same paragraph reports the numbers and says the effect did not appear in that run.
