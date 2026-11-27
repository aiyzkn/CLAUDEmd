# job-resume-check.ps1 — SessionStart フック（Windows）
# カレントディレクトリの .jobs/ に「完了したが未報告」の long-run ジョブがあれば、その旨を出力する。
# 出力（stdout）はセッションのコンテキストに入る。該当が無ければ何も出さない。
# フック自体が失敗してもセッションを止めないよう、常に exit 0 で終える。
try {
    $source = 'unknown'
    if ([Console]::IsInputRedirected) {
        $stdin = [Console]::In.ReadToEnd()
        if ($stdin -match '"source"\s*:\s*"(\w+)"') { $source = $Matches[1] }
    }
    # プロジェクトが同名のフックを持つ場合は、通知が二重にならないよう何もしない
    if (Test-Path -LiteralPath '.claude/hooks/job-resume-check.ps1') { exit 0 }
    if (-not (Test-Path -LiteralPath '.jobs')) { exit 0 }

    $pending = foreach ($d in Get-ChildItem -LiteralPath '.jobs' -Directory) {
        $exitFile = Join-Path $d.FullName 'exit.code'
        if ((Test-Path -LiteralPath $exitFile) -and -not (Test-Path -LiteralPath (Join-Path $d.FullName 'collected'))) {
            '  - {0}（exit={1}）' -f $d.Name, (Get-Content -Raw -LiteralPath $exitFile).Trim()
        }
    }
    if (-not $pending) { exit 0 }

    $longRun = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts\long-run.ps1'
    $msg = @('完了したがユーザーへ未報告の long-run ジョブがある:') + @($pending)
    if ($source -eq 'resume') {
        $msg += '中断前の会話の続きとして、各ジョブの output.log を確認し、結果をユーザーへ報告する。'
    } else {
        $msg += '会話履歴が無いので、先に各ジョブの intent.md（完了後にやること）を読み、output.log を確認してから結果をユーザーへ報告する。'
    }
    $msg += ('報告した後で powershell -NoProfile -ExecutionPolicy Bypass -File "{0}" claim -Id <ジョブID> を実行し、報告済みにする（しないと毎回通知される）。' -f $longRun)
    $msg += 'ユーザーが最初のメッセージで別の作業を頼んでいる場合はそちらを優先し、未報告のジョブがあることだけを 1 行で伝える。'

    $bytes = [Text.Encoding]::UTF8.GetBytes(($msg -join "`n"))
    $out = [Console]::OpenStandardOutput()
    $out.Write($bytes, 0, $bytes.Length)
    $out.Flush()
} catch {
    [Console]::Error.WriteLine("job-resume-check: $_")
}
exit 0
