#!/bin/bash
# git-auto-commit.sh — 自动暂存并提交所有变更
#
# 2026-10-08 修复说明：
#   原实现把运行日志写在仓库内的 evolution/git-commit.log，且该文件被 git 跟踪。
#   于是每次提交都会改写它 → 被 fswatch 视为新变化 → 再次提交，形成自引用死循环。
#   yunnan-comm-agent-team 因此累积 31,492 次提交 / 11.3 GB 的 .git。
#   现在日志改写到仓库之外的 ~/Library/Logs/agent-git/，从结构上杜绝该循环。
#
# 用法：bash scripts/git-auto-commit.sh [可选提交信息]

BASE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BASE" || exit 1

TEAM="$(basename "$BASE")"
LOGDIR="$HOME/Library/Logs/agent-git"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/$TEAM.log"

PENDING="$BASE/evolution/pending-commit.txt"

# 是否自动推送到 GitHub。默认 false —— 只做本地提交，不自动推送。
AUTO_PUSH="${AUTO_PUSH:-false}"

# 确保守护脚本始终有执行权限
chmod +x "$BASE/scripts/git-watcher-daemon.sh" 2>/dev/null || true

# 无变更则跳过（.DS_Store 等已被 .gitignore 忽略，不计入）
if git diff --quiet && git diff --staged --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    exit 0
fi

if [ -n "$1" ]; then
    MSG="$1"
elif [ -f "$PENDING" ] && [ -s "$PENDING" ]; then
    MSG=$(cat "$PENDING")
    rm -f "$PENDING"
else
    CHANGED=$(git diff --name-only; git ls-files --others --exclude-standard | head -5)
    COUNT=$(echo "$CHANGED" | grep -c . || echo 0)
    MSG="[AUTO] $(date '+%Y-%m-%d %H:%M') 自动提交·${COUNT}个文件变更"
fi

git add -A
git commit -m "$MSG" >> "$LOG" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ commit $(git rev-parse --short HEAD): $MSG" >> "$LOG"
    if [ "$AUTO_PUSH" = "true" ] && git remote get-url origin &>/dev/null; then
        git push origin main >> "$LOG" 2>&1
        if [ $? -eq 0 ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] ☁️  push 成功 → GitHub" >> "$LOG"
        else
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️  push 失败（网络问题？），本地 commit 已保留" >> "$LOG"
        fi
    fi
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ commit 失败或无变更：$MSG" >> "$LOG"
fi

exit $EXIT_CODE
