"""Download Gemma 4 31B's SWE-bench Lite run published by another team (spec/third-party-lite.md): each issue's final
patch (rollouts/<issue>/<attempt>/preds.json), the grading summary and the run's metadata. Not the transcripts or
token logs (about 2.3 GB).

    python pull_third_party_lite.py OUT_DIR
"""
import sys

from huggingface_hub import snapshot_download

REPO = "dougalldeepmind/2026-10-10-swebench-gemma4-lite-gemma-v2"
SHA = "1c5f3d3be50e4ca6ceb17654987fd34e6cf23f96"
p = snapshot_download(REPO, repo_type="dataset", revision=SHA, local_dir=sys.argv[1], max_workers=16,
                      allow_patterns=["README.md", "results/results.json", "results/results.md",
                                      "results/grading/*.json", "metadata/config.yaml", "metadata/manifest.json",
                                      "metadata/frozen_recipe.json", "rollouts/*/*/preds.json",
                                      "rollouts/*/*/exit_status.yaml", "rollouts/*/*/done.json"])
print(p)
