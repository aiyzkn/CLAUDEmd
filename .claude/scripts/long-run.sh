#!/usr/bin/env bash
# long-run.sh — 長時間かかるコマンドを、Claude Code のセッションから切り離して実行する（Linux / macOS）
#
#   start  --name <名前> --command "<コマンド>" [--intent "<完了後にやること>"]
#   status [--id <ジョブID>]
#   log    --id <ジョブID> [--lines <行数>]
#   claim  --id <ジョブID>
#
# ジョブはカレントディレクトリの .jobs/<日時>_<名前>/ に置く（中身は long-run.ps1 と同じ）。
# 起動には setsid（無ければ nohup）を使い、呼び出し元のセッションから切り離す。
set -euo pipefail

action="${1:-}"; shift || true
name=""; command=""; intent=""; id=""; lines=40; root=".jobs"
while [ $# -gt 0 ]; do
  case "$1" in
    --name) name="$2"; shift 2 ;;
    --command) command="$2"; shift 2 ;;
    --intent) intent="$2"; shift 2 ;;
    --id) id="$2"; shift 2 ;;
    --lines) lines="$2"; shift 2 ;;
    --root) root="$2"; shift 2 ;;
    *) echo "不明な引数: $1" >&2; exit 2 ;;
  esac
done

job_dir() {
  [ -d "$root/$1" ] || { echo "ジョブが見つからない: $1" >&2; exit 1; }
  (cd "$root/$1" && pwd)
}

job_state() {
  local d="$1"
  if [ -f "$d/exit.code" ]; then
    local s="完了 exit=$(tr -d '[:space:]' < "$d/exit.code")"
    if [ -f "$d/collected" ]; then echo "$s（報告済み）"; else echo "$s（未報告）"; fi
  elif [ -f "$d/pid" ]; then
    local p; p="$(tr -d '[:space:]' < "$d/pid")"
    if kill -0 "$p" 2>/dev/null; then echo "実行中 pid=$p"; else echo "停止（exit.code が無いまま pid=$p が終了した）"; fi
  else
    echo "起動前"
  fi
}

case "$action" in
  start)
    [ -n "$name" ] && [ -n "$command" ] || { echo "start には --name と --command が必要" >&2; exit 2; }
    [[ "$name" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "--name は英数字・_・.・- のみ" >&2; exit 2; }
    job_id="$(date +%Y%m%d_%H%M%S)_$name"
    mkdir -p "$root/$job_id"
    dir="$(cd "$root/$job_id" && pwd)"
    printf '%s\n' "$command" > "$dir/command.sh"
    [ -n "$intent" ] || intent="（未記入）完了後にやることが記録されていない。output.log を読み、何のためのジョブかをユーザーに確認する。"
    printf '# %s\n\n## 完了後にやること\n\n%s\n\n## 実行したコマンド\n\n```bash\n%s\n```\n' "$job_id" "$intent" "$command" > "$dir/intent.md"
    cat > "$dir/run.sh" <<EOF
#!/usr/bin/env bash
cd "$(pwd)"
bash "$dir/command.sh" >> "$dir/output.log" 2>&1
echo \$? > "$dir/exit.code"
EOF
    if command -v setsid >/dev/null 2>&1; then
      setsid bash "$dir/run.sh" < /dev/null > /dev/null 2>&1 &
    else
      nohup bash "$dir/run.sh" < /dev/null > /dev/null 2>&1 &
    fi
    echo $! > "$dir/pid"
    echo "起動した: $job_id（pid=$!）"
    echo "状態: bash \"$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/long-run.sh\" status --id $job_id"
    ;;
  status)
    if [ -n "$id" ]; then
      d="$(job_dir "$id")"; echo "$id  $(job_state "$d")"
    elif [ -d "$root" ] && [ -n "$(ls -A "$root")" ]; then
      for d in "$root"/*/; do d="${d%/}"; echo "$(basename "$d")  $(job_state "$d")"; done
    else
      echo "ジョブは無い"
    fi
    ;;
  log)
    [ -n "$id" ] || { echo "log には --id が必要" >&2; exit 2; }
    d="$(job_dir "$id")"
    if [ -f "$d/output.log" ]; then tail -n "$lines" "$d/output.log"; else echo "（出力はまだ無い）"; fi
    ;;
  claim)
    [ -n "$id" ] || { echo "claim には --id が必要" >&2; exit 2; }
    d="$(job_dir "$id")"
    [ -f "$d/exit.code" ] || { echo "まだ完了していない: $id" >&2; exit 1; }
    date -u +%Y-%m-%dT%H:%M:%SZ > "$d/collected"
    echo "報告済みにした: $id"
    ;;
  *)
    sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
