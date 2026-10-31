#!/usr/bin/env bash
# PostToolUse(Edit|Write): collector/ 아래 .py 파일을 ruff로 검사한다.
# 파일을 수정하지 않도록 --fix는 쓰지 않는다.
set -u

file_path=$(python3 -c '
import json
import sys

try:
    data = json.load(sys.stdin)
    print(data["tool_input"]["file_path"])
except (ValueError, KeyError, TypeError):
    pass
')

project_dir="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
collector_dir="$project_dir/collector"

[ -f "$collector_dir/pyproject.toml" ] || exit 0

case "$file_path" in
  /*) ;;
  *) file_path="$project_dir/$file_path" ;;
esac

case "$file_path" in
  "$collector_dir"/*.py) ;;
  *) exit 0 ;;
esac

[ -f "$file_path" ] || exit 0

if ! output=$(cd "$collector_dir" && uv run ruff check "$file_path" 2>&1); then
  printf '%s\n' "$output" >&2
  exit 2
fi
