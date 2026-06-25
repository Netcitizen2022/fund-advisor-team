#!/bin/bash
# stage_b_check.sh — fund-advisor-team 阶段B环境检查 v1.0
BASE="$(cd "$(dirname "$0")/.." && pwd)"
TEAM_NAME="$(basename "$BASE")"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}[OK]${NC}   $1"; }
skip() { echo -e "  ${YELLOW}[SKIP]${NC}  $1"; }
run()  { echo -e "  ${BLUE}[RUN]${NC}   $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC}  $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC}  $1"; }

echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  $TEAM_NAME -- Stage B 环境检查${NC}"
echo -e "${BLUE}  $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${BLUE}============================================${NC}"

# Step 0: 前置状态预检
echo ""
echo -e "${BLUE}[Step 0] 前置状态预检${NC}"

SCRIPTS_OK=0
if [ -f "$BASE/scripts/git-auto-commit.sh" ] && \
   [ -f "$BASE/scripts/git-watcher-daemon.sh" ] && \
   [ -f "$BASE/scripts/setup-git-watcher.sh" ]; then
  skip "脚本三件套已就位"
  SCRIPTS_OK=1
else
  warn "脚本三件套不完整"
fi

SSH_OK=0
SSH_OUT=$(ssh -o ConnectTimeout=5 -T git@github.com 2>&1)
if echo "$SSH_OUT" | grep -q "successfully authenticated"; then
  skip "SSH → GitHub 已通"
  SSH_OK=1
else
  warn "SSH → GitHub 不通"
fi

GIT_OK=0
if [ -d "$BASE/.git" ]; then
  LAST=$(git -C "$BASE" log --oneline -1 2>/dev/null || echo "无提交记录")
  skip "Git 已初始化（最近提交: $LAST）"
  GIT_OK=1
else
  warn "Git 尚未初始化"
fi

REMOTE_OK=0
REMOTE_URL=$(git -C "$BASE" remote get-url origin 2>/dev/null)
if [ -n "$REMOTE_URL" ]; then
  skip "GitHub remote 已连接（$REMOTE_URL）"
  REMOTE_OK=1
else
  warn "GitHub remote 未配置"
fi

WATCHER_OK=0
if ps aux | grep "git-watcher-daemon" | grep -v grep | grep -q "$TEAM_NAME"; then
  skip "fswatch 守护进程已运行"
  WATCHER_OK=1
else
  warn "fswatch 守护进程未运行"
fi

echo ""
echo -e "${BLUE}[1] fswatch${NC}"
if /opt/homebrew/bin/fswatch --version >/dev/null 2>&1; then
  VER=$(/opt/homebrew/bin/fswatch --version 2>&1 | head -1 | tr -d '\n')
  skip "fswatch 已安装 -- $VER"
else
  run "brew install fswatch"
  brew install fswatch
  /opt/homebrew/bin/fswatch --version >/dev/null 2>&1 && ok "fswatch 安装成功" || fail "fswatch 安装失败"
fi

echo ""
echo -e "${BLUE}[2] Python 解释器${NC}"
PYTHON_CMD=""
for cmd in python3 python; do
  if command -v "$cmd" >/dev/null 2>&1; then
    PYTHON_CMD="$cmd"
    PY_VER=$($cmd --version 2>&1 | tr -d '\n')
    skip "$PY_VER  (命令: $cmd)"
    break
  fi
done
[ -z "$PYTHON_CMD" ] && fail "Python 未找到" && exit 1

echo ""
echo -e "${BLUE}[3] python-docx${NC}"
VER=$($PYTHON_CMD -m pip show python-docx 2>/dev/null | grep "^Version:" | awk '{print $2}')
if [ -n "$VER" ]; then
  skip "python-docx 已安装 -- v$VER"
else
  run "python3 -m pip install python-docx --break-system-packages"
  $PYTHON_CMD -m pip install python-docx --break-system-packages --quiet
  VER2=$($PYTHON_CMD -m pip show python-docx 2>/dev/null | grep "^Version:" | awk '{print $2}')
  [ -n "$VER2" ] && ok "python-docx 安装成功 -- v$VER2" || fail "python-docx 安装失败"
fi

echo ""
echo -e "${BLUE}[4] 脚本三件套权限${NC}"
if [ "$SCRIPTS_OK" -eq 1 ]; then
  chmod +x "$BASE/scripts/git-auto-commit.sh" \
           "$BASE/scripts/git-watcher-daemon.sh" \
           "$BASE/scripts/setup-git-watcher.sh"
  git -C "$BASE" config core.fileMode false 2>/dev/null || true
  git -C "$BASE" update-index --chmod=+x \
    scripts/git-watcher-daemon.sh \
    scripts/git-auto-commit.sh 2>/dev/null || true
  ok "权限已设置"
else
  warn "脚本三件套不完整，跳过"
fi

echo ""
echo -e "${BLUE}[5] Git 初始化${NC}"
if [ "$GIT_OK" -eq 1 ]; then
  skip "Git 已初始化，跳过"
else
  git -C "$BASE" init
  git -C "$BASE" config core.fileMode false
  git -C "$BASE" add -A
  git -C "$BASE" commit -m "init: $TEAM_NAME v1.0" 2>/dev/null || true
  ok "Git 仓库已初始化"
fi

echo ""
echo -e "${BLUE}[6] GitHub 远程仓库${NC}"
if [ "$REMOTE_OK" -eq 1 ]; then
  skip "remote 已连接，跳过"
else
  warn "请手动执行（先在 GitHub 建空仓库）："
  echo -e "    git remote add origin git@github.com:Netcitizen2022/fund-advisor-team.git"
  echo -e "    git branch -M main"
  echo -e "    git push -u origin main"
fi

echo ""
echo -e "${BLUE}[7] fswatch 守护进程${NC}"
if [ "$WATCHER_OK" -eq 1 ]; then
  skip "守护进程已运行，跳过"
else
  DAEMON="$BASE/scripts/git-watcher-daemon.sh"
  if [ -f "$DAEMON" ]; then
    bash "$BASE/scripts/setup-git-watcher.sh"
    sleep 1
    PID2=$(ps aux | grep "git-watcher-daemon" | grep -v grep | awk '{print $2}' | head -1)
    [ -n "$PID2" ] && ok "守护进程启动成功 -- PID $PID2" || fail "守护进程启动失败"
  else
    warn "未找到 $DAEMON"
  fi
fi

echo ""
echo -e "${BLUE}[8] ~/.zshrc 自动保活${NC}"
if grep -q "_start_watcher" ~/.zshrc 2>/dev/null && grep -q "$TEAM_NAME" ~/.zshrc 2>/dev/null; then
  skip "~/.zshrc 已配置（含本项目）"
else
  warn "请将以下一行加入 ~/.zshrc："
  echo -e "    _start_watcher $BASE"
fi

echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  Stage B 检查完成${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo -e "  全链路验证："
echo -e "    echo '部署验证' >> evolution/session-log.md"
echo -e "    sleep 8 && tail -5 evolution/git-commit.log"
echo ""
