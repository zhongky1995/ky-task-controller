#!/bin/zsh
set -eu

repo_dir=${0:A:h}
codex_bin="/Applications/ChatGPT.app/Contents/Resources/codex"

if [[ ! -x "$codex_bin" ]]; then
  codex_bin="$(command -v codex || true)"
fi

if [[ -z "$codex_bin" || ! -x "$codex_bin" ]]; then
  echo "未找到支持插件管理的 Codex。请先安装或更新 Codex Desktop。"
  read -r "?按回车键关闭..."
  exit 1
fi

echo "正在添加 KY-TASK 开源市场..."
"$codex_bin" plugin marketplace add "$repo_dir"

echo "正在安装 task-controller..."
"$codex_bin" plugin add task-controller@ky-task-controller

echo ""
echo "安装完成。请完全新建一个 Codex 任务后使用 KY-TASK。"
read -r "?按回车键关闭..."
