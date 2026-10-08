#!/bin/bash
# git-watcher-daemon.sh — 监听目录变化并自动提交
#
# 2026-10-08 修复说明（对照 OneDrive 版正常实现）：
#   1. 排除 .DS_Store / ._* 噪音 —— 原先没有排除，iCloud 与 Finder 会频繁触碰
#      这些文件，成为死循环的触发器。
#   2. 日志移到仓库外，提交本身不再产生新的可监听变化。
#   3. 防抖延迟由 3 秒提高到 10 秒，并排除 node_modules / __pycache__。
#
# 本脚本位于 <团队>/scripts/ 下，自动探测团队根目录。

BASE="$(cd "$(dirname "$0")/.." && pwd)"
COMMIT_SCRIPT="$BASE/scripts/git-auto-commit.sh"
PIDFILE="$BASE/evolution/.watcher.pid"

TEAM="$(basename "$BASE")"
LOGDIR="$HOME/Library/Logs/agent-git"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/$TEAM.log"

# 防重复启动
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; then
    exit 0
fi
echo $$ > "$PIDFILE"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🟢 Git 监听守护进程启动 PID=$$，监听目录：$BASE" >> "$LOG"

trap 'rm -f "$PIDFILE"; echo "[$(date +%Y-%m-%d\ %H:%M:%S)] 🔴 守护进程退出 PID=$$" >> "$LOG"' EXIT

/opt/homebrew/bin/fswatch \
  --event=Updated \
  --event=Created \
  --event=Removed \
  --exclude='\.git/' \
  --exclude='\.DS_Store' \
  --exclude='^\._' \
  --exclude='git-commit\.log' \
  --exclude='pending-commit\.txt' \
  --exclude='\.watcher\.pid' \
  --exclude='node_modules' \
  --exclude='__pycache__' \
  --latency=10 \
  -o \
  "$BASE" \
| while read -r count; do
    bash "$COMMIT_SCRIPT"
done
