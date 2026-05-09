#!/usr/bin/env bash
# install.sh — 将 srt-summarizer skill 注册到 Claude Code
#
# 用法:
#   chmod +x install.sh && ./install.sh
#   bash install.sh
#   bash install.sh --uninstall    # 移除注册
#
# 注册方式: 在 ~/.claude/skills/ 下创建指向本项目的软链接。
# Claude Code 启动时自动发现该目录下的 skill。

set -euo pipefail

SKILL_NAME="srt-summarizer"
SKILLS_DIR="${HOME}/.claude/skills"
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="${SKILLS_DIR}/${SKILL_NAME}"

# ---- 颜色 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
RESET='\033[0m'

msg_ok()  { printf "${GREEN}%s${RESET} %s\n" "✓" "$1"; }
msg_warn(){ printf "${YELLOW}%s${RESET} %s\n" "⚠" "$1"; }
msg_err() { printf "${RED}%s${RESET} %s\n" "✗" "$1"; }
msg_hdr() { printf "\n${BOLD}==>${RESET} %s\n" "$1"; }

# ---- 卸载 ----
do_uninstall() {
    msg_hdr "卸载 srt-summarizer skill"
    if [ -L "${TARGET}" ]; then
        rm "${TARGET}"
        msg_ok "已移除软链接: ${TARGET}"
    elif [ -e "${TARGET}" ]; then
        msg_err "${TARGET} 不是软链接，请手动处理"
        exit 1
    else
        msg_warn "未找到注册项，无需卸载"
    fi
    exit 0
}

[ "${1:-}" = "--uninstall" ] && do_uninstall

# ---- 安装 ----
echo ""
printf "${BOLD}srt-summarizer skill 安装${RESET}\n"
echo "──────────────────────────────────────────────"

# 1. 检查 Python 核心依赖
msg_hdr "检查 Python 核心依赖"
if python3 -c "import re, os, json, datetime" 2>/dev/null; then
    msg_ok "Python 3 标准库可用"
else
    msg_err "Python 3 不可用，请先安装 Python 3.10+"
    exit 1
fi

# 2. 创建 skills 目录
msg_hdr "注册 skill"
mkdir -p "${SKILLS_DIR}"

# 3. 处理已有注册
if [ -L "${TARGET}" ]; then
    current_target="$(readlink "${TARGET}")"
    if [ "${current_target}" = "${SKILL_DIR}" ]; then
        msg_warn "已注册且指向当前目录，跳过"
    else
        msg_warn "已有注册指向 ${current_target}，替换为当前目录"
        rm "${TARGET}"
        ln -s "${SKILL_DIR}" "${TARGET}"
        msg_ok "已更新软链接: ${TARGET} -> ${SKILL_DIR}"
    fi
elif [ -e "${TARGET}" ]; then
    msg_err "${TARGET} 已存在且不是软链接，请手动处理"
    exit 1
else
    ln -s "${SKILL_DIR}" "${TARGET}"
    msg_ok "已创建软链接: ${TARGET} -> ${SKILL_DIR}"
fi

# 4. 检查可选依赖
msg_hdr "检查可选依赖"
if python3 -c "import cv2" 2>/dev/null; then
    msg_ok "opencv-python 可用（视频抽帧）"
else
    msg_warn "opencv-python 未安装（视频抽帧不可用）"
    echo "       安装: pip install opencv-python"
fi

if python3 -c "from PIL import Image" 2>/dev/null; then
    msg_ok "Pillow 可用（图示渲染）"
else
    msg_warn "Pillow 未安装（图示渲染不可用）"
    echo "       安装: pip install Pillow"
fi

# 5. 检查字体
msg_hdr "检查字体"
if [ -f "${SKILL_DIR}/fonts/HarmonyOS_Sans_SC_Medium.ttf" ]; then
    msg_ok "中文字体可用"
else
    msg_warn "中文字体缺失，图示渲染将降级为系统字体"
fi

# ---- 完成 ----
echo ""
printf "${GREEN}${BOLD}==> 安装完成${RESET}\n"
echo "    重启 Claude Code 后可使用: /srt-summarizer <路径>"
echo ""
echo "    卸载: bash ${SKILL_DIR}/install.sh --uninstall"
