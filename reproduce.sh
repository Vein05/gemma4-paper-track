#!/usr/bin/env bash
# Recompute the paper's claims from the released data. No GPU and no model calls.
#   ./reproduce.sh main         the main paper's claims
#   ./reproduce.sh supplement   the supplement's claims (not written yet)
#   ./reproduce.sh all          both
# Downloads only the files those analyses read, into .reproduce/, and leaves the repository's own files unchanged.
set -euo pipefail
cd "$(dirname "$0")"

usage() { sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
[ $# -eq 1 ] || usage
case "$1" in main|supplement|all) ;; *) usage ;; esac

supplement() {
  echo "The supplement's claims are not covered yet. Run ./reproduce.sh main for the main paper." >&2
  exit 2
}
[ "$1" = supplement ] && supplement

# Same package versions the committed summaries were made with.
PACKAGES="numpy==2.4.4 scipy==1.17.1 pyarrow==24.0.0 scikit-learn==1.8.0"
VENV=.reproduce/venv
if [ ! -x "$VENV/bin/python" ]; then
  mkdir -p .reproduce
  if command -v uv >/dev/null; then
    uv venv -q --python 3.12 "$VENV"
    # shellcheck disable=SC2086
    uv pip install -q --python "$VENV/bin/python" $PACKAGES
  else
    python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || { echo "Needs Python 3.11 or newer, or uv." >&2; exit 1; }
    python3 -m venv "$VENV"
    # shellcheck disable=SC2086
    "$VENV/bin/python" -m pip install -q $PACKAGES
  fi
fi

"$VENV/bin/python" scripts/reproduce_main.py
[ "$1" = all ] && supplement
exit 0
