# Rubber Stamp: Gemma 4 Checks Other Agents' Patches Well and Its Own Poorly

Code, data and outputs for a submission to the paper track of the Gemma 4 Developer Agent competition on Kaggle.

## Finding

Nine open models rated 388 SWE-bench Verified patches for the chance that each passes its hidden tests. The judge saw
the issue and one patch, never the author. Gemma 4 31B ranks other agents' patches well (AUROC 0.83) and its own
poorly (0.64), below a 9B outside judge (0.76). Five other models that wrote patches show no such gap.

The cause is rubber-stamping: Gemma gives 110 of its 150 own patches the top score of 100, including 49 of its 80
failing ones. Its scores still order its own attempts at one issue about as well as outside judges do.

Draft writeup: `paper/writeup.md`.

## Layout

| Path | Contents |
|---|---|
| `paper/writeup.md` | draft writeup |
| `spec/` | analysis plans, each written before its data was computed |
| `scripts/` | rating and analysis code |
| `scripts/derived/` | per-call judge outputs (`selfpref_*.jsonl`) and the summaries behind every number |
| `data/public/` | Gemma 4 agent patches and control patches with their SWE-bench labels (sources in `data/README.md`) |
| `citations.md` | cited works, copied from primary sources |

## Reproduce

Analyses need no API calls and read only `scripts/derived/`:

```bash
pip install numpy scipy
python3 scripts/self_judging_replication.py   # self-judging gap, Section 3.1
python3 scripts/own_patch_mechanism.py        # Sections 3.2–3.4
python3 scripts/self_check_fix.py             # Section 3.5
```

Rating the patches again calls models through OpenRouter (`scripts/self_preference.py`, needs `OPENROUTER_API_KEY`);
the study cost $3.70.

## Data

All inputs are public: SWE-bench Verified Mini, Gemma 4 31B agent runs published on Hugging Face by a third party,
and mini-SWE-agent submissions from SWE-bench experiments. Revisions and licenses are listed in `data/README.md`.
No competition data is used.
