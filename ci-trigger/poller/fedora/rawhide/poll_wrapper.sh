#!/bin/bash
set -e
trap "echo '🛑 Poller stopping...'; exit 0" SIGINT SIGTERM

LOG_FILE="${POLLER_LOG_FILE:-/var/log/poller.log}"

# Ensure our state and data directories exist inside the container
mkdir -p /etc/poller-data/state

while true; do
    echo "[poller] $(date +'%Y-%m-%d %H:%M:%S') === Starting Fedora RAWHIDE poll cycle ===" >> "$LOG_FILE"
    
    # Execute the Python payload
    python3 /opt/ci-trigger/poller/payload.py >> "$LOG_FILE" 2>&1
    
    exit_code=$?
    if [ $exit_code -eq 1 ]; then
        echo "⚠️ [poller] New Fedora builds detected! Triggering test matrix." >> "$LOG_FILE"
    else
        echo "✅ [poller] No new builds found. Sleeping until next cycle." >> "$LOG_FILE"
    fi

    # Wait 15 minutes before checking again to avoid Docker Hub throttling
    sleep 900 
done
