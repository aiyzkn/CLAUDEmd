#!/usr/bin/env bash
# detect-tools.sh — 外部コマンドの所在・版・文字コード環境を調べ、~/.claude/tool-environment.json に書く（Linux / macOS）
#
#   bash detect-tools.sh [追加のコマンド名...]
#
# JSON の組み立てに python3 があれば使い、既存の "notes" を引き継ぐ。無ければ notes は引き継がない。
set -u
out="${TOOL_ENV_OUT:-$HOME/.claude/tool-environment.json}"   # TOOL_ENV_OUT で書き出し先を変えられる（試験用）
tools="git gh python3 python uv node npm npx bun deno pwsh bash zsh brew apt mise podman docker docker-compose pandoc pdftotext jq rg curl cargo rustc go java dotnet code dot rtk $*"

first_line() {
  local exe="$1" arg="$2" t=""
  command -v timeout >/dev/null 2>&1 && t="timeout 5"
  $t "$exe" $arg 2>&1 | tr -d '\r' | grep -m1 -v '^[[:space:]]*$' | cut -c1-200
}

esc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }

entries=""
found_n=0; missing=""
for t in $(printf '%s\n' $tools | awk '!seen[$0]++'); do
  p="$(command -v "$t" 2>/dev/null || true)"
  if [ -z "$p" ]; then
    entries="$entries\"$t\": {\"found\": false},"
    missing="$missing $t"; continue
  fi
  case "$t" in go) a="version" ;; java) a="-version" ;; dot) a="-V" ;; *) a="--version" ;; esac
  v="$(first_line "$p" "$a")"
  entries="$entries\"$t\": {\"found\": true, \"path\": \"$(esc "$p")\", \"version\": \"$(esc "$v")\"},"
  found_n=$((found_n + 1))
done

json="{\"generated\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"os\": {\"platform\": \"$(uname -s | tr 'A-Z' 'a-z')\", \"version\": \"$(esc "$(uname -sr)")\"}, \"encoding\": {\"lang\": \"$(esc "${LANG:-}")\", \"lc_all\": \"$(esc "${LC_ALL:-}")\"}, \"tools\": {${entries%,}}}"

mkdir -p "$(dirname "$out")"
if command -v python3 >/dev/null 2>&1; then
  printf '%s' "$json" | python3 -c '
import json, sys, os
doc = json.load(sys.stdin)
out = sys.argv[1]
if os.path.exists(out):
    try:
        doc["notes"] = json.load(open(out, encoding="utf-8")).get("notes")
    except Exception:
        pass
open(out, "w", encoding="utf-8").write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
' "$out"
else
  printf '%s\n' "$json" > "$out"
fi
echo "書き込んだ: $out"
echo "見つかった: $found_n 件 / 見つからない:${missing:- なし}"
