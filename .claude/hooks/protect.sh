#!/bin/bash
# PreToolUse 保护钩子:阻止 Claude 修改敏感文件(路径含 .env 或 secret)
# 由 .claude/settings.json 的 PreToolUse hook(matcher: Edit|Write)调用:
#   - stdin 收到本次工具调用的 JSON(含 tool_input.file_path)
#   - 命中敏感路径 → stderr 输出原因 + 退出码 2 → 拦截本次 Edit/Write
#   - 未命中 → 退出码 0,放行

input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // empty')

if [ -n "$file_path" ] && echo "$file_path" | grep -qiE '(\.env|secret)'; then
  echo "已拦截:禁止修改敏感文件 $file_path(如确需变更,请人工手动编辑)" >&2
  exit 2
fi

exit 0
