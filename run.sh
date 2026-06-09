#!/bin/bash
# Hermes News — hourly refresh runner with health monitoring
cd ~/hermes-news || { echo "FAIL: cd ~/hermes-news" >> /tmp/hermes-news.log; exit 1; }

LOG=/tmp/hermes-news.log
HEALTH=/tmp/hermes-news-health.json
NOW=$(date "+%Y-%m-%d %H:%M")

echo "[$NOW] Starting..." >> "$LOG"

# Run scraper
python3 scripts/refresh_news.py >> "$LOG" 2>&1
SCRIPT_OK=$?

if [ $SCRIPT_OK -ne 0 ]; then
    echo "WARN: Script exit code $SCRIPT_OK at $NOW" >> "$LOG"
    # Still try to push — previous HTML might be fine
fi

# Record health status
echo "{\"last_run\":\"$NOW\",\"exit_code\":$SCRIPT_OK,\"page\":\"https://caesaryin2026.github.io/hermes-agent-news/\"}" > "$HEALTH"

# Push to GitHub
git add -A
if git diff --cached --quiet; then
    echo "No changes" >> "$LOG"
else
    git commit -m "auto $(date +%H:%M)" >> "$LOG" 2>&1
    git pull --rebase origin main >> "$LOG" 2>&1 || true
    git push origin main >> "$LOG" 2>&1 && echo "Pushed OK" >> "$LOG"
fi

# Health check: verify page was updated recently
LAST_PUB=$(stat -c %Y hermes-news.html 2>/dev/null || echo 0)
NOW_TS=$(date +%s)
AGE=$((NOW_TS - LAST_PUB))
if [ $AGE -gt 7200 ]; then
    echo "WARN: Page is $AGE seconds old (>2h)!" >> "$LOG"
fi

echo "[$(date "+%Y-%m-%d %H:%M")] Done" >> "$LOG"
