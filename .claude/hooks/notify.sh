#!/usr/bin/env bash
# notify.sh — Notification フック（Linux / macOS）。動作は notify.ps1 と同じ。
# macOS は osascript、Linux は notify-send で通知する。どちらも無ければ何もしない。
# 常に exit 0 で終え、通知の失敗で Claude Code を止めない。
input="$(cat 2>/dev/null || true)"

# JSON は python で読む（jq を前提にしない）。python が無ければ既定の文言を使う
read_field() {
  printf '%s' "$input" | python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get(sys.argv[1]) or "", end="")
except Exception:
    pass' "$1" 2>/dev/null
}
title="$(read_field title)"; title="${title:-Claude Code}"
message="$(read_field message)"; message="${message:-入力を待っています}"
cwd="$(read_field cwd)"
[ -n "$cwd" ] && title="$title — $(basename "$cwd")"

if command -v osascript >/dev/null 2>&1; then
  # AppleScript の文字列リテラルに入れるため、バックスラッシュと二重引用符をエスケープする
  esc() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'; }
  osascript -e "display notification \"$(esc "$message")\" with title \"$(esc "$title")\"" >/dev/null 2>&1
elif command -v notify-send >/dev/null 2>&1; then
  notify-send "$title" "$message" >/dev/null 2>&1
fi
exit 0
