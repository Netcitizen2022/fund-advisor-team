#!/bin/bash
# git-watcher-daemon.sh
# 自动探测团队根目录（本脚本位于 <团队>/scripts/ 下）
BASE="$(cd "$(dirname "$0")/.." && pwd)"
COMMIT_SCRIPT="$BASE/scripts/git-auto-commit.sh"
PIDFILE="$BASE/evolution/.watcher.pid"
LOG="$BASE/evolution/git-commit.log"

if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        exit 0
    fi
fi
echo $$ > "$PIDFILE"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🟢 Git 监听守护进程启动 PID=$$，监听目录：$BASE" >> "$LOG"

trap 'rm -f "$PIDFILE"; echo "[$(date +%Y-%m-%d\ %H:%M:%S)] 🔴 守护进程退出 PID=$$" >> "$LOG"' EXIT

/opt/homebrew/bin/fswatch \
  --event=Updated \
  --event=Created \
  --event=Removed \
  --exclude='\.git' \
  --exclude='git-commit\.log' \
  --exclude='pending-commit\.txt' \
  --exclude='\.watcher\.pid' \
  --latency=3 \
  -o \
  "$BASE" \
| while read -r count; do
    bash "$COMMIT_SCRIPT"
done
