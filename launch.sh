#!/usr/bin/env bash
# Daily Intel run script.
#
#   ./launch.sh              generate reports, push to origin, publish public page, open locally
#   ./launch.sh --no-open    skip opening the browser (for automation / cron)
#   ./launch.sh --no-push    skip the git commit/push (also skips publishing)
#   ./launch.sh --no-publish push to the private origin but skip the public GitHub Pages update
#
# Outputs per run:
#   daily-reports/YYYY/MM/DD/daily-intel-YYYY-MM-DD.md    (archived Markdown)
#   daily-reports/YYYY/MM/DD/daily-intel-YYYY-MM-DD.html  (archived styled HTML)
#   reports/uniphore-daily-intel.html                     (private canonical permalink)
#   public/index.html                                     (copy published to Pages)
#
# The public page is served (free) from a separate PUBLIC repo via GitHub Pages:
#   https://sandramiley-aitransformation.github.io/uniphore-daily-intel/
# The private repo (source, archive, script) stays private.
set -euo pipefail
cd "$(dirname "$0")"

# Public Pages repo that mirrors public/index.html at its root.
PUBLIC_REMOTE="https://github.com/sandramiley-AITransformation/uniphore-daily-intel.git"
PAGES_URL="https://sandramiley-aitransformation.github.io/uniphore-daily-intel/"

DO_OPEN=1
DO_PUSH=1
DO_PUBLISH=1
for arg in "$@"; do
  case "$arg" in
    --no-open) DO_OPEN=0 ;;
    --no-push) DO_PUSH=0 ;;
    --no-publish) DO_PUBLISH=0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

# 1. Generate Markdown + HTML archives, the canonical permalink, and public/index.html.
echo "▸ Generating reports…"
OUTPUTS="$(python3 generate_report.py)"
while IFS= read -r line; do echo "  wrote $line"; done <<< "$OUTPUTS"
MD_PATH="$(printf '%s\n' "$OUTPUTS" | grep '\.md$' | head -1)"
EDITION="$(basename "$MD_PATH" .md | sed 's/^daily-intel-//')"

# 2. Commit and push the reports to the PRIVATE origin.
if [[ "$DO_PUSH" -eq 1 ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "▸ Committing and pushing to private origin…"
    git add -A
    git commit -m "Archive Daily Intel report for ${EDITION}

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>" >/dev/null
    BRANCH="$(git rev-parse --abbrev-ref HEAD)"
    git push origin "$BRANCH"
    echo "  pushed to origin/${BRANCH}"
  else
    echo "▸ No changes to push — working tree clean."
  fi

  # 3. Publish public/index.html to the PUBLIC Pages repo (renders on click).
  if [[ "$DO_PUBLISH" -eq 1 ]]; then
    echo "▸ Publishing public page to GitHub Pages…"
    TMP="$(mktemp -d)"
    trap 'rm -rf "$TMP"' EXIT
    git clone --depth 1 -q "$PUBLIC_REMOTE" "$TMP"
    # Sync the whole public/ tree: latest index.html, editions/, archive.html.
    cp -R public/. "$TMP/"
    ( cd "$TMP"
      if [[ -n "$(git status --porcelain)" ]]; then
        git add -A
        git -c user.name="Sandra Miley" -c user.email="dan.miley@gmail.com" \
          commit -q -m "Publish Daily Intel report for ${EDITION}

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
        git push -q origin HEAD:main
        echo "  published → ${PAGES_URL}"
      else
        echo "  public page already up to date."
      fi )
  else
    echo "▸ Skipping public publish (--no-publish)."
  fi
else
  echo "▸ Skipping push (--no-push); public publish also skipped."
fi

# 4. Open the live edition locally.
if [[ "$DO_OPEN" -eq 1 ]]; then
  open index.html
fi
