#!/bin/bash
# setup-git-watcher.sh
BASE="$(cd "$(dirname "$0")/.." && pwd)"
DAEMON="$BASE/scripts/git-watcher-daemon.sh"

chmod +x "$DAEMON"
chmod +x "$BASE/scripts/git-auto-commit.sh"

git -C "$BASE" config core.fileMode false
git -C "$BASE" update-index --chmod=+x scripts/git-watcher-daemon.sh scripts/git-auto-commit.sh 2>/dev/null || true

pgrep -f "$DAEMON" > /dev/null || nohup bash \
  "$DAEMON" \
  >> "$BASE/evolution/git-commit.log" 2>&1 &

echo "守护进程已启动，PID: $!  （监听目录：$BASE）"
echo ""
echo "重启 Mac 后请将以下一行加入 ~/.zshrc 实现自动保活："
echo "  _start_watcher $BASE"
