#!/bin/bash
cd ~/hermes-news || exit 1

# Ensure SSH agent has the key
eval $(ssh-agent -s) > /dev/null 2>&1
ssh-add ~/.ssh/github_dog 2>/dev/null || true

# Run the scraper
python3 scripts/refresh_news.py >> /tmp/hermes-news.log 2>&1

# Push to GitHub
git add -A
if git diff --cached --quiet; then
    echo "No changes to commit" >> /tmp/hermes-news.log
else
    git commit -m "auto $(date +%H:%M)" >> /tmp/hermes-news.log 2>&1
    git pull --rebase origin main >> /tmp/hermes-news.log 2>&1
    git push origin main >> /tmp/hermes-news.log 2>&1
fi

echo "--- Done at $(date) ---" >> /tmp/hermes-news.log
