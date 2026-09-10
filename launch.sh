#!/usr/bin/env bash
# Daily Intel run script.
#
#   ./launch.sh            generate today's Markdown report, push to origin, open locally
#   ./launch.sh --no-open  generate + push, skip opening the browser (for automation)
#   ./launch.sh --no-push  generate + open, skip the git commit/push
#
# The Markdown report is archived under daily-reports/YYYY/MM/DD/ using the
# edition date from index.html.
set -euo pipefail
cd "$(dirname "$0")"

DO_OPEN=1
DO_PUSH=1
for arg in "$@"; do
  case "$arg" in
    --no-open) DO_OPEN=0 ;;
    --no-push) DO_PUSH=0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

# 1. Generate the Markdown report into its date-ordered location.
echo "▸ Generating Markdown report…"
REPORT_PATH="$(python3 generate_report.py)"
echo "  wrote $REPORT_PATH"

# 2. Commit and push the report (and any index.html changes) to origin.
if [[ "$DO_PUSH" -eq 1 ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    EDITION="$(basename "$REPORT_PATH" .md | sed 's/^daily-intel-//')"
    echo "▸ Committing and pushing to origin…"
    git add -A
    git commit -m "Archive Daily Intel report for ${EDITION}

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>" >/dev/null
    BRANCH="$(git rev-parse --abbrev-ref HEAD)"
    git push origin "$BRANCH"
    echo "  pushed to origin/${BRANCH}"
  else
    echo "▸ No changes to push — working tree clean."
  fi
else
  echo "▸ Skipping push (--no-push)."
fi

# 3. Open the live edition locally.
if [[ "$DO_OPEN" -eq 1 ]]; then
  open index.html
fi
