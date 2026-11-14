#!/bin/bash
# deploy.sh - Pull the latest main, update dependencies and restart the web app.
#
# Runs on the server as an SSH forced command (see README "CI/CD"), so it takes
# no arguments and ignores SSH_ORIGINAL_COMMAND.
#
# The whole body lives in main() and the script exits right after calling it:
# bash reads scripts incrementally, and `git pull` may rewrite this very file.

set -euo pipefail

APP_DIR="/home/edu/job-scraper"
SERVICE="job-scraper-web"
HEALTH_RETRIES=10
HEALTH_INTERVAL=2

main() {
    cd "$APP_DIR"

    local old_commit new_commit
    old_commit=$(git rev-parse HEAD)
    git pull --ff-only
    new_commit=$(git rev-parse HEAD)

    if ! git diff --quiet "$old_commit" "$new_commit" -- requirements.txt; then
        echo "requirements.txt changed, installing dependencies"
        venv/bin/pip install -r requirements.txt
    fi

    # -n: fail instead of prompting if the sudoers rule is missing
    sudo -n systemctl restart "$SERVICE"

    # PORT from .env (plain KEY=value lines); never source the file here
    local port=""
    if [ -f .env ]; then
        port=$(sed -n 's/^PORT=//p' .env | tail -n 1 | tr -d '[:space:]')
    fi
    port="${port:-5000}"

    local attempt
    for attempt in $(seq 1 "$HEALTH_RETRIES"); do
        sleep "$HEALTH_INTERVAL"
        if curl -fsS -o /dev/null "http://localhost:${port}/"; then
            echo "Health check passed on port ${port}"
            echo "Deployed $(git rev-parse --short HEAD)"
            return 0
        fi
        echo "Health check attempt ${attempt}/${HEALTH_RETRIES} failed"
    done

    echo "Health check failed: http://localhost:${port}/ did not respond" >&2
    return 1
}

main
exit
