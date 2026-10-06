# Spec: an outside judge as the check of Gemma 4's own patches

Written 2026-10-06 17:50 CDT, before this analysis was computed. **Exploratory**: every score it uses already exists,
and the AUROC of each judge on Gemma's patches in the held-out issues was printed (point estimates only) before this
spec was written. Terms follow `GLOSSARY.md`. No model calls; no cost.

## Question

The draft's practical advice (`paper/writeup.md` §4) is that a second model checks Gemma's finished patches better
than Gemma does. It rested on the Mini issues with Gemma's patches from four harnesses. Does it hold on the
held-out issues and on the Mini issues with matched-harness patches, and which outside judges does it hold for?

## Patches and labels

Gemma's own patches scored by all nine judges (same prompt `Q_P1`, settings and parser as
`spec/self-judging-replication.md`):

1. Held-out issues (`spec/fresh-replication.md`): runs main-a and main-b; labels from `fresh_judging.labels` (issues
   whose reference patch resolves on Magnolia). Scores in `derived/fresh_<tag>.jsonl`.
2. Mini issues, matched harness (`spec/mini50-same-harness.md`): run mini50, same labels rule; `django__django-11848`
   left out (its label predates its graded patch).
3. Mini issues, four harnesses (original study, `derived/selfpref_<tag>.jsonl`), for reference.

## Measures

- For each of the eight outside judges k: AUROC of k on Gemma's patches minus AUROC of Gemma on the same patches.
- The same for the mean score of the eight outside judges (eight calls per patch).
- Gemma plus judge k: the mean of the two judges' percentile ranks of the scores, minus Gemma alone (two calls per
  patch).
- 95% intervals from 2,000 resamples of issues (seed 0); also the 99.375% interval (95% Bonferroni over the eight
  outside judges).
- Cost per call of each judge from the `cost` field of the held-out rows.

## Reading

A judge counts as a better check on a patch set if the lower bound of its 95% interval is above 0. Because the analysis
is exploratory and compares eight judges, the paper reports the Bonferroni interval beside it and names no judge as
best unless it is better on the held-out issues, the largest set.
