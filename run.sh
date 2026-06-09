#!/bin/bash
# Hermes News — hourly refresh runner with self-healing
cd ~/hermes-news || { echo "FAIL: cd ~/hermes-news" >> /tmp/hermes-news.log; exit 1; }

LOG=/tmp/hermes-news.log
HEARTBEAT=/tmp/hermes-news-heartbeat
HEALTH=/tmp/hermes-news-health.json
NOW=$(date "+%Y-%m-%d %H:%M")
MAX_RETRIES=3
RETRY_DELAY=600  # 10 minutes between retries

echo "[$NOW] Starting..." >> "$LOG"

# Run scraper with retry
for attempt in $(seq 1 $MAX_RETRIES); do
    python3 scripts/refresh_news.py >> "$LOG" 2>&1
    SCRIPT_OK=$?
    if [ $SCRIPT_OK -eq 0 ]; then
        echo "OK on attempt $attempt" >> "$LOG"
        # Write heartbeat timestamp
        date +%s > "$HEARTBEAT"
        break
    fi
    if [ $attempt -lt $MAX_RETRIES ]; then
        echo "Attempt $attempt failed (code $SCRIPT_OK). Retry in ${RETRY_DELAY}s..." >> "$LOG"
        sleep $RETRY_DELAY
    else
        echo "All $MAX_RETRIES attempts failed at $NOW" >> "$LOG"
    fi
done

# Record health status
echo "{\"last_run\":\"$NOW\",\"exit_code\":$SCRIPT_OK}" > "$HEALTH"

# Push to GitHub (always try, even if script had partial failures)
git add -A
if git diff --cached --quiet; then
    echo "No changes" >> "$LOG"
else
    git commit -m "auto $(date +%H:%M)" >> "$LOG" 2>&1
    git pull --rebase origin main >> "$LOG" 2>&1 || true
    git push origin main >> "$LOG" 2>&1 && echo "Pushed OK" >> "$LOG"
fi

echo "[$(date "+%Y-%m-%d %H:%M")] Done" >> "$LOG"
