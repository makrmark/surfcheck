#!/bin/bash
# surfcheck deploy script — generate report, commit, and push to GitHub Pages
# Called by launchd at 5:45 AM daily

set -e
cd "$(dirname "$0")"

# Load API keys from outside the repo (OPENROUTER_API_KEY, etc.)
ENV_FILE="$HOME/.surforecast/env.sh"
if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
fi

LOG_FILE="$HOME/surfcheck_deploy.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $*" >> "$LOG_FILE"
}

log "=== surfcheck deploy start ==="

# Generate the report
./venv/bin/python surf_report.py >> "$LOG_FILE" 2>&1
REPORT_EXIT=$?

if [ $REPORT_EXIT -ne 0 ]; then
    log "ERROR: surf_report.py failed with exit code $REPORT_EXIT"
    exit 1
fi

# Commit and push
git add -A >> "$LOG_FILE" 2>&1
git commit -m "Daily surf report $(date '+%Y-%m-%d')" >> "$LOG_FILE" 2>&1 || log "Nothing new to commit"
git push >> "$LOG_FILE" 2>&1

log "=== surfcheck deploy complete ==="
