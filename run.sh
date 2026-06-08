#!/bin/bash
cd ~/hermes-news || { echo "FAIL: cd ~/hermes-news"; exit 1; }

echo "[$(date "+%Y-%m-%d %H:%M")] Starting..." >> /tmp/hermes-news.log

# Run scraper
python3 scripts/refresh_news.py >> /tmp/hermes-news.log 2>&1
SCRIPT_OK=$?

if [ $SCRIPT_OK -ne 0 ]; then
    echo "WARN: Script exit code $SCRIPT_OK" >> /tmp/hermes-news.log
fi

# Push to GitHub (SSH key handles auth via ~/.ssh/config)
git add -A
if git diff --cached --quiet; then
    echo "No changes" >> /tmp/hermes-news.log
else
    git commit -m "auto $(date +%H:%M)" >> /tmp/hermes-news.log 2>&1
    git pull --rebase origin main >> /tmp/hermes-news.log 2>&1 || true
    git push origin main >> /tmp/hermes-news.log 2>&1 && echo "Pushed OK" >> /tmp/hermes-news.log
fi

echo "[$(date "+%Y-%m-%d %H:%M")] Done" >> /tmp/hermes-news.log
