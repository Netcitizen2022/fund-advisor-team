#!/bin/bash
# git-auto-commit.sh
# 自动探测团队根目录（本脚本位于 <团队>/scripts/ 下，无需手改路径）
BASE="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$BASE/evolution/git-commit.log"
PENDING="$BASE/evolution/pending-commit.txt"

cd "$BASE" || exit 1

chmod +x "$BASE/scripts/git-watcher-daemon.sh" 2>/dev/null || true

if git diff --quiet && git diff --staged --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 无变更，跳过提交" >> "$LOG"
    exit 0
fi

if [ -f "$PENDING" ] && [ -s "$PENDING" ]; then
    MSG=$(cat "$PENDING")
    rm -f "$PENDING"
else
    CHANGED=$(git diff --name-only && git ls-files --others --exclude-standard | head -5)
    COUNT=$(echo "$CHANGED" | grep -c . || echo "0")
    DATE=$(date '+%Y-%m-%d %H:%M')
    MSG="[AUTO] $DATE 自动提交·${COUNT}个文件变更"
fi

git update-index --chmod=+x scripts/git-watcher-daemon.sh scripts/git-auto-commit.sh 2>/dev/null || true
git add -A
git commit -m "$MSG"

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    HASH=$(git rev-parse --short HEAD)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ commit $HASH: $MSG" >> "$LOG"

    if git remote get-url origin &>/dev/null; then
        git push origin main >> "$LOG" 2>&1
        if [ $? -eq 0 ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] ☁️  push 成功 → GitHub" >> "$LOG"
        else
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️  push 失败（网络问题？），本地 commit 已保留" >> "$LOG"
        fi
    fi
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ commit 失败：$MSG" >> "$LOG"
fi

exit $EXIT_CODE
