#!/usr/bin/env bash
# file-lock.sh — ファイルを書き込み・削除しにくい状態にする（Linux / macOS）
#
#   lock   <パス...>     ロックする（ディレクトリは配下のファイルをすべて対象にする）
#   unlock [<パス...>]   指定したファイルのロックを外す。省略するとすべて外す
#   status               ロック中のファイルを表示する
#
# 仕組みと強さ（Windows 版のような強制ロックは Unix に標準では無いため、使える手段を重ねる）:
#   共通           書き込み権限を外す（chmod a-w）。元の権限は記録して unlock で戻す
#   macOS          chflags uchg も付ける。所有者でも変更・削除・改名ができなくなる（root 不要）
#   Linux（root）  chattr +i も付ける。変更・削除・改名ができなくなる
#   Linux（一般）  chmod だけ。書き込みは拒否されるが、所有者が権限を戻せば書ける。
#                  削除はディレクトリの権限で決まるため防げない
# 再起動してもロックは外れない（unlock で外す）。
set -euo pipefail

state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/claude-file-lock"
list="$state_dir/files.tsv"          # 1 行 1 ファイル: <元の権限>\t<フラグ（無ければ -）>\t<絶対パス>
max_files=1000
os="$(uname -s)"
action="${1:-}"; shift || true

abspath() { (cd "$(dirname "$1")" && printf '%s/%s\n' "$(pwd)" "$(basename "$1")"); }
get_mode() { stat -c %a "$1" 2>/dev/null || stat -f %Lp "$1"; }

expand() {
  for p in "$@"; do
    [ -e "$p" ] || { echo "見つからない: $p" >&2; exit 1; }
    if [ -d "$p" ]; then find "$p" -type f -print | while IFS= read -r f; do abspath "$f"; done
    else abspath "$p"; fi
  done
}

is_locked() { [ -f "$list" ] && awk -F'\t' -v f="$1" '$3==f{found=1} END{exit !found}' "$list"; }

lock_one() {
  local f="$1" mode flags="-"
  mode="$(get_mode "$f")"
  if [ "$os" = "Darwin" ]; then
    chflags uchg "$f" && flags="uchg"
  elif [ "$(id -u)" = "0" ] && command -v chattr >/dev/null 2>&1; then
    chattr +i "$f" && flags="immutable"
  fi
  chmod a-w "$f" 2>/dev/null || true   # uchg / immutable の後は chmod できないことがある
  printf '%s\t%s\t%s\n' "$mode" "$flags" "$f" >> "$list"
}

unlock_line() {
  local mode="$1" flags="$2" f="$3"
  [ -e "$f" ] || { echo "（既に無い）$f"; return; }
  case "$flags" in
    uchg) chflags nouchg "$f" ;;
    immutable) chattr -i "$f" ;;
  esac
  chmod "$mode" "$f"
}

case "$action" in
  lock)
    [ $# -gt 0 ] || { echo "lock にはパスが必要" >&2; exit 2; }
    mkdir -p "$state_dir"; touch "$list"
    targets="$(expand "$@")"
    total=$(( $(wc -l < "$list") + $(printf '%s\n' "$targets" | wc -l) ))
    [ "$total" -le "$max_files" ] || { echo "対象が $total 件ある。上限は $max_files 件" >&2; exit 1; }
    n=0
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      is_locked "$f" && continue
      lock_one "$f"; n=$((n + 1))
    done <<< "$targets"
    echo "ロックした: $n 件（合計 $(wc -l < "$list") 件）"
    if [ "$os" != "Darwin" ] && [ "$(id -u)" != "0" ]; then
      echo "注意: Linux の一般ユーザーでは書き込み権限を外すだけで、削除は防げない"
    fi
    ;;
  unlock)
    [ -s "$list" ] || { echo "ロック中のファイルは無い"; exit 0; }
    tmp="$(mktemp)"; n=0
    if [ $# -gt 0 ]; then targets="$(expand "$@")"; else targets=""; fi
    while IFS=$'\t' read -r mode flags f; do
      if [ -z "$targets" ] || printf '%s\n' "$targets" | grep -qxF -- "$f"; then
        unlock_line "$mode" "$flags" "$f"; n=$((n + 1))
      else
        printf '%s\t%s\t%s\n' "$mode" "$flags" "$f" >> "$tmp"
      fi
    done < "$list"
    mv "$tmp" "$list"
    echo "ロックを外した: $n 件 / 残り: $(wc -l < "$list") 件"
    ;;
  status)
    if [ ! -s "$list" ]; then echo "ロック中のファイルは無い"; exit 0; fi
    echo "ロック中: $(wc -l < "$list") 件"
    while IFS=$'\t' read -r mode flags f; do
      echo "  $f（元の権限 $mode$([ "$flags" = "-" ] || printf "・%s" "$flags")）"
    done < "$list"
    ;;
  *)
    sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
