#!/usr/bin/env bash
# agent-skills-profile 一键部署 / 同步（macOS / Linux）
#
# 做的事和 install.ps1 一样：clone-or-pull 本仓库 -> 合并 AGENTS.md（保留本机
# codebase-memory-mcp 标记块）-> 按 deploy-manifest.txt 同步 skill 软链接
# -> 按需装 codebase-memory-mcp / officecli 两个外部工具。可以重复运行。
#
# 用法：
#   ./scripts/install.sh                          # 完整安装/同步
#   SKIP_TOOLS=1 ./scripts/install.sh             # 只同步 skill 链接
#   REPO_PATH=~/dev/agent-skills-profile ./scripts/install.sh   # 自定义位置

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/77652189/agent-skills-profile.git}"
REPO_PATH="${REPO_PATH:-$HOME/Documents/Codex/agent-skills-profile}"
SKIP_TOOLS="${SKIP_TOOLS:-0}"

step() { printf '\n==> %s\n' "$1"; }

# --- 1. clone 或 pull ----------------------------------------------------

if [ -d "$REPO_PATH/.git" ]; then
  step "拉取最新: $REPO_PATH"
  git -C "$REPO_PATH" pull --ff-only
else
  step "克隆到: $REPO_PATH"
  mkdir -p "$(dirname "$REPO_PATH")"
  git clone "$REPO_URL" "$REPO_PATH"
fi

# --- 2. 合并 AGENTS.md，保留本机 codebase-memory-mcp 标记块 ---------------

step "同步 AGENTS.md -> ~/.codex/AGENTS.md"

MARKER="<!-- codebase-memory-mcp:start -->"
LIVE_AGENTS="$HOME/.codex/AGENTS.md"
mkdir -p "$HOME/.codex"

awk -v marker="$MARKER" '$0==marker{exit} {print}' "$REPO_PATH/AGENTS.md" > /tmp/codex-profile-agents-head.$$

if [ -f "$LIVE_AGENTS" ] && grep -qF "$MARKER" "$LIVE_AGENTS"; then
  awk -v marker="$MARKER" 'f{print} $0==marker{f=1; print}' "$LIVE_AGENTS" > /tmp/codex-profile-agents-tail.$$
else
  awk -v marker="$MARKER" 'f{print} $0==marker{f=1; print}' "$REPO_PATH/AGENTS.md" > /tmp/codex-profile-agents-tail.$$
fi

cat /tmp/codex-profile-agents-head.$$ /tmp/codex-profile-agents-tail.$$ > "$LIVE_AGENTS"
rm -f /tmp/codex-profile-agents-head.$$ /tmp/codex-profile-agents-tail.$$

# --- 3. 按 deploy-manifest.txt 同步 skill 软链接 --------------------------

step "同步 skills（按 deploy-manifest.txt）"

mapfile -t MANIFEST < <(grep -vE '^\s*(#|$)' "$REPO_PATH/deploy-manifest.txt" | sed 's/[[:space:]]*$//')

for home_dir in "$HOME/.codex/skills" "$HOME/.claude/skills"; do
  mkdir -p "$home_dir"

  # 3a. 建缺的链接
  for name in "${MANIFEST[@]}"; do
    src="$REPO_PATH/skills/$name"
    [ -d "$src" ] || src="$REPO_PATH/skills/matt-pocock/$name"
    if [ ! -d "$src" ]; then
      echo "警告: 清单里的 '$name' 在 skills/ 和 skills/matt-pocock/ 下都找不到，跳过" >&2
      continue
    fi
    link="$home_dir/$name"
    if [ -L "$link" ] && [ "$(readlink "$link")" = "$src" ]; then
      continue
    fi
    rm -rf "$link"
    ln -sfn "$src" "$link"
    echo "  + $name"
  done

  # 3b. 拆清单里已经没有、但本地还链接着（指向本仓库）的
  for link in "$home_dir"/*/; do
    [ -L "${link%/}" ] || continue
    name="$(basename "$link")"
    target="$(readlink -f "$link")"
    case " ${MANIFEST[*]} " in
      *" $name "*) continue ;;
    esac
    case "$target" in
      "$REPO_PATH/skills/"*)
        rm -f "${link%/}"
        echo "  - $name（清单里已移除）"
        ;;
    esac
  done
done

# --- 4. 外部工具 -----------------------------------------------------------

if [ "$SKIP_TOOLS" != "1" ]; then
  step "检查外部工具"

  if command -v codebase-memory-mcp >/dev/null 2>&1; then
    echo "  codebase-memory-mcp 已装，跳过"
  else
    echo "  安装 codebase-memory-mcp..."
    curl -fsSL https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.sh | bash
  fi

  if command -v officecli >/dev/null 2>&1; then
    echo "  officecli 已装，跳过"
  else
    echo "  安装 officecli..."
    curl -fsSL https://d.officecli.ai/install.sh | bash
    # 安装脚本会往 ~/.claude/skills/officecli 扔一份独立文件；换成指向仓库的软链接
    officecli_link="$HOME/.claude/skills/officecli"
    if [ -e "$officecli_link" ] && [ ! -L "$officecli_link" ]; then
      rm -rf "$officecli_link"
      ln -sfn "$REPO_PATH/skills/officecli" "$officecli_link"
    fi
  fi
else
  echo -e "\n(已跳过外部工具检查，见 SKIP_TOOLS=1)"
fi

step "完成"
echo "重启 Codex / Claude Code 会话让改动生效。"
