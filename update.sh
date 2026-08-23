#!/bin/sh
# Re-pull the sheet and rebuild the page. Run this after anyone edits the sheet.
set -e
cd "$(dirname "$0")"
python3 build/refresh.py "$@"
python3 build/build.py
python3 build/smoke.py
echo
echo "Done. Commit and push to publish:"
echo "  git add -A && git commit -m 'Refresh from sheet' && git push"
