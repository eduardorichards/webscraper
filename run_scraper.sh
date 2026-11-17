#!/bin/bash
# run_scraper.sh - Wrapper for cron execution
# Usage: Add to crontab:
#   0 * * * * /home/edu/job-scraper/run_scraper.sh                  (LinkedIn)
#   45 6 * * * /home/edu/job-scraper/run_scraper.sh --source ats    (ATS boards)
# Arguments are passed to main.py. All runs share one lock, so a LinkedIn run
# and an ATS run never write to the database at the same time: whichever
# starts second skips.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"

# Load environment config (plain KEY=value lines, see .env.example)
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

# LOG_DIR: relative paths resolve from the project root (same as config/env.py)
LOG_DIR="${LOG_DIR:-data/logs}"
case "$LOG_DIR" in
    /*) ;;
    *) LOG_DIR="$PROJECT_DIR/$LOG_DIR" ;;
esac
LOCK_FILE="$LOG_DIR/scraper.lock"
LOG_FILE="$LOG_DIR/cron.log"

mkdir -p "$LOG_DIR"

# Shown in the log lines, e.g. " (--source ats)"; empty without arguments
RUN_ARGS=""
if [ "$#" -gt 0 ]; then
    RUN_ARGS=" ($*)"
fi

# Prevent overlapping runs
if [ -f "$LOCK_FILE" ]; then
    LOCK_PID=$(cat "$LOCK_FILE")
    if kill -0 "$LOCK_PID" 2>/dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Scraper already running (PID $LOCK_PID), skipping run$RUN_ARGS." >> "$LOG_FILE"
        exit 0
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Stale lock file found, removing." >> "$LOG_FILE"
        rm -f "$LOCK_FILE"
    fi
fi

# Write lock file
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

# Activate virtualenv
source "$VENV_DIR/bin/activate"

# Run scraper
echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting scraper run$RUN_ARGS" >> "$LOG_FILE"
cd "$PROJECT_DIR"
python main.py "$@" >> "$LOG_FILE" 2>&1
echo "$(date '+%Y-%m-%d %H:%M:%S') - Scraper run finished$RUN_ARGS" >> "$LOG_FILE"
