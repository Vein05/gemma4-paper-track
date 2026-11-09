# Spec: does Gemma's extra trust in its own failing patches remain against equally strong writers?

Written 2026-11-09, before any patch in this set was scored in this run. Approved by the user (2026-11-09, "$10 added,
let's just run the first one"). Background and cost: `notes/more-writers-run-2026-11-09.md`.

## Why

The paper's split by writer strength was chosen after the per-writer table was seen, and its strong group holds three
writers. Pombal et al. (2026, Appendix H) matched comparison writers on ability for contest programs and medical
answers and report that self-preference "attenuates in places but never disappears". This run makes the same
comparison for Gemma 4 31B on agent patches, with the writers chosen by a rule that uses labels only.

The run has two stages. This spec fixes both. Only stage 1 is paid for and started now.

## Writers (rule fixed before scoring; applied with labels only)

Source: every mini-SWE-agent entry on SWE-bench Verified in `SWE-bench/experiments` (commit `40f164d5`) that the paper
does not already use, with patches from the public `swe-bench-submissions` bucket and labels from each entry's
`per_instance_details.json`. Downloaded by `scripts/matched_writers.py fetch` to
`data/public/swe-bench-verified-more-writers/`. Patches go through the paper's filters: test files removed, empty
patches and patches over 30,000 characters dropped. Issues are the paper's 193 held-out issues.

An entry is left out if it has no resolved issue at all (its labels are unusable: Gemini 3 Pro "high") or usable
patches for fewer than half the issues (Claude 3.7 Sonnet; Gemini 3.5 Flash has no patches in the bucket).

A writer's resolve rate is its passing patches over its usable patches on these issues. Gemma's is 54.0% (101 of 187).

**Stage 1, equally strong writers:** every writer, new or among the paper's five, whose resolve rate is within 8
points of Gemma's. The rule gives seven writers in four families (`scripts/derived/matched_writers_selection.json`):

| Writer | Family | Resolve rate | Failing patches |
|---|---|---|---|
| o3 (mini-SWE-agent 1.0.0) | OpenAI | 61.7% | 72 |
| GLM-4.5 (in the paper) | Zhipu | 61.0% | 64 |
| GPT-5 mini (mini-SWE-agent 2.0.0) | OpenAI | 59.4% | 76 |
| Kimi-K2 (in the paper) | Moonshot | 59.2% | 58 |
| Gemini 2.5 Pro | Google | 55.5% | 81 |
| GPT-5 nano | OpenAI | 48.1% | 82 |
| o4-mini | OpenAI | 48.0% | 93 |

With Gemma's own 86 failing patches the set has 612 patches (`scripts/derived/matched_patches.jsonl`). Only failing
patches are scored, because every claim under test is about failing patches. The counts differ a little from the
paper's (82 own failing, 54 and 61 for Kimi-K2 and GLM-4.5) because the paper counts patches that all nine judges
scored in October, and this set is fixed before scoring.

**Stage 2, every other writer:** the failing patches of the 26 remaining usable entries and of the paper's other three
writers (Qwen3-Coder, gpt-oss-120b, Llama-4-Maverick), about 2,000 patches, scored the same way.

## Judging

The nine judges of the paper's held-out analysis, on OpenRouter, with the prompt, settings and parser of
`scripts/fresh_judging.py`: one pass with a 3,000-token limit, then one more ask at 8,000 tokens for answers without a
parsed score, as in the October run. Providers are not pinned, as in October. Gemma's own failing patches and the
failing patches of Kimi-K2 and GLM-4.5 are scored again in this run, so that every comparison is between scores from
the same session. Script `scripts/matched_writers.py run`; rows `scripts/derived/matched_<judge>.jsonl`.

Cost estimate for stage 1: $4.50 to $6.50. The run stops if the spend passes $8.

## Measures

Extra trust on a patch is Gemma's score minus the mean of the outside judges on the same patch. The outside judges are
the other eight, without judges of the writer's family. The two gpt-oss judges count as the family of the OpenAI
writers. Patches scored by all nine judges are used. Intervals are 95%, from 2,000 resamples of issues, seed 0.

1. **Primary: own minus equally strong writers, with families weighted equally.** Mean extra trust on Gemma's own
   failing patches, minus the mean over the four families of each family's mean, where a family's mean is the mean of
   its writers' means. OpenAI then counts for a quarter of the comparison and not for 60% of the patches.
2. The same with all patches pooled.
3. The same with each family left out in turn. The version without Google matters most: Gemini is from Gemma's maker.
4. Measures 1 to 3 with the share of patches that Gemma scores 100 in place of extra trust.
5. Per writer: failing patches, Gemma's mean score, the outside mean, extra trust, share scored 100.
6. Drift: for the patches scored in October too, the mean shift and mean absolute difference per judge, and extra
   trust on Gemma's own and on Kimi-K2's and GLM-4.5's failing patches, October against now.

## Reading, fixed now

On measure 1:

- **No detectable preference against equally strong writers:** the interval includes 0.
- **Shrinks but remains:** the interval is above 0 and the estimate is below 9.9, the lower end of the interval of
  the paper's gap against all writers (16.3, 9.9 to 22.7). This agrees with Pombal et al.
- **Writer strength does not explain the gap among equally strong writers:** the estimate is 9.9 or more. The paper's
  title and first contribution then need to change.

If the result without Google or without OpenAI falls in a different reading than measure 1, the paper reports that the
result depends on the family mix.

Stage 2 is run only if the user approves its cost after seeing stage 1. Its measures are fixed here: extra trust per
writer against resolve rate across all writers, a fit of extra trust on resolve rate with a term per family, the
predicted value at Gemma's resolve rate against Gemma's own, and the same-edit test of `spec/belief-vs-recognition.md`
on the larger set.

## Guess before the run

Measure 1 between 3 and 10, about 65% likely to read "shrinks but remains" or "no detectable preference". The paper's
exploratory number against three strong writers is +9.2 (2.1 to 16.0).

## Logging

Changelog entry with the OpenRouter cost; W&B group `matched-writers` (from this Mac); analysis
`scripts/derived/matched_writers_2026-11-09.json`. No GPU.
