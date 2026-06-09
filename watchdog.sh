#!/bin/bash
# Watchdog - checks if news refresh is healthy
HEARTBEAT=/tmp/hermes-news-heartbeat
LOG=/tmp/hermes-news-watchdog.log
NOW=$(date +%s)
MAX_AGE=7200  # 2 hours max since last heartbeat

if [ ! -f "$HEARTBEAT" ]; then
    echo "[$(date)] WARN: No heartbeat file" >> "$LOG"
    exit 1
fi

LAST=$(cat "$HEARTBEAT")
AGE=$((NOW - LAST))

if  [ $AGE -gt $MAX_AGE ] ; then
    echo "[$(date)] ALERT: Heartbeat is $AGEs old (>$MAX_AGE s). Restarting..." >> "$LOG"
    qd
    cd || exit 1
    bash run.sh
else
    echo "[$(date)] OK: Heartbeat $AGEs ago" >> "$LOG"
fi