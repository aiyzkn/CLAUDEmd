#!/usr/bin/env bash
# job-resume-check.sh — SessionStart フック（Linux / macOS）。動作は job-resume-check.ps1 と同じ。
# 常に exit 0 で終え、フックの失敗でセッションを止めない。
input="$(cat 2>/dev/null || true)"
source="unknown"
case "$input" in *'"source"'*'"resume"'*) source="resume" ;; esac

[ -f .claude/hooks/job-resume-check.sh ] && exit 0
[ -d .jobs ] || exit 0

pending=""
for d in .jobs/*/; do
  d="${d%/}"
  [ -f "$d/exit.code" ] && [ ! -f "$d/collected" ] || continue
  pending="$pending
  - $(basename "$d")（exit=$(tr -d '[:space:]' < "$d/exit.code")）"
done
[ -n "$pending" ] || exit 0

long_run="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/long-run.sh"
echo "完了したがユーザーへ未報告の long-run ジョブがある:$pending"
if [ "$source" = "resume" ]; then
  echo "中断前の会話の続きとして、各ジョブの output.log を確認し、結果をユーザーへ報告する。"
else
  echo "会話履歴が無いので、先に各ジョブの intent.md（完了後にやること）を読み、output.log を確認してから結果をユーザーへ報告する。"
fi
echo "報告した後で bash \"$long_run\" claim --id <ジョブID> を実行し、報告済みにする（しないと毎回通知される）。"
echo "ユーザーが最初のメッセージで別の作業を頼んでいる場合はそちらを優先し、未報告のジョブがあることだけを 1 行で伝える。"
exit 0
