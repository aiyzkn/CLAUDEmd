# long-run.ps1 — 長時間かかるコマンドを、Claude Code のセッションから切り離して実行する（Windows）
#
#   start  -Name <名前> -Command "<コマンド>" [-Intent "<完了後にやること>"]
#   status [-Id <ジョブID>]
#   log    -Id <ジョブID> [-Lines <行数>]
#   claim  -Id <ジョブID>
#
# ジョブはカレントディレクトリの .jobs/<日時>_<名前>/ に置く。中身:
#   command.ps1  実行するコマンド       intent.md  完了後にやること
#   output.log   標準出力と標準エラー   pid        実行中のプロセス ID
#   exit.code    終了コード（完了の印） collected  報告済みの印（claim で作る）
#
# 起動には WMI（Win32_Process.Create）を使う。呼び出し元のプロセスツリーから外れるため、
# Claude Code のセッションが終わってもジョブは止まらない。
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet('start', 'status', 'log', 'claim')]
    [string]$Action,
    [string]$Name,
    [string]$Command,
    [string]$Intent,
    [string]$Id,
    [int]$Lines = 40,
    [string]$Root = '.jobs'
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }   # Git Bash から呼ばれても日本語が化けないように
$Utf8Bom = New-Object System.Text.UTF8Encoding($true)

function Get-JobDir([string]$jobId) {
    $d = Join-Path $Root $jobId
    if (-not (Test-Path -LiteralPath $d)) { throw "ジョブが見つからない: $jobId" }
    return (Resolve-Path -LiteralPath $d).Path
}

function Get-JobState([string]$dir) {
    if (Test-Path -LiteralPath (Join-Path $dir 'exit.code')) {
        $code = (Get-Content -Raw -LiteralPath (Join-Path $dir 'exit.code')).Trim()
        $state = "完了 exit=$code"
        if (Test-Path -LiteralPath (Join-Path $dir 'collected')) { $state += '（報告済み）' } else { $state += '（未報告）' }
        return $state
    }
    $pidFile = Join-Path $dir 'pid'
    if (Test-Path -LiteralPath $pidFile) {
        $p = [int](Get-Content -Raw -LiteralPath $pidFile).Trim()
        if (Get-Process -Id $p -ErrorAction SilentlyContinue) { return "実行中 pid=$p" }
        return "停止（exit.code が無いまま pid=$p が終了した）"
    }
    return '起動前'
}

switch ($Action) {
    'start' {
        if (-not $Name -or -not $Command) { throw 'start には -Name と -Command が必要' }
        if ($Name -notmatch '^[A-Za-z0-9_.-]+$') { throw '-Name は英数字・_・.・- のみ' }
        $jobId = '{0}_{1}' -f (Get-Date -Format 'yyyyMMdd_HHmmss'), $Name
        $dir = Join-Path (New-Item -ItemType Directory -Force -Path $Root).FullName $jobId
        New-Item -ItemType Directory -Path $dir | Out-Null
        $log = Join-Path $dir 'output.log'
        $exitFile = Join-Path $dir 'exit.code'

        [IO.File]::WriteAllText((Join-Path $dir 'command.ps1'), $Command + "`r`n", $Utf8Bom)
        if (-not $Intent) { $Intent = '（未記入）完了後にやることが記録されていない。output.log を読み、何のためのジョブかをユーザーに確認する。' }
        $intentDoc = "# $jobId`r`n`r`n## 完了後にやること`r`n`r`n$Intent`r`n`r`n## 実行したコマンド`r`n`r`n``````powershell`r`n$Command`r`n```````r`n"
        [IO.File]::WriteAllText((Join-Path $dir 'intent.md'), $intentDoc, $Utf8Bom)

        # ラッパー: コマンドを実行し、出力をログへ、終了コードを exit.code へ書く
        $runner = @"
`$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath '$((Get-Location).Path -replace "'", "''")'
`$code = 0
try {
    & '$((Join-Path $dir 'command.ps1') -replace "'", "''")' *>&1 | Out-File -FilePath '$($log -replace "'", "''")' -Encoding utf8 -Append
    if (`$LASTEXITCODE) { `$code = `$LASTEXITCODE } elseif (-not `$?) { `$code = 1 }
} catch {
    `$_ | Out-File -FilePath '$($log -replace "'", "''")' -Encoding utf8 -Append
    `$code = 1
}
Set-Content -LiteralPath '$($exitFile -replace "'", "''")' -Value `$code -Encoding ascii
"@
        $runnerPath = Join-Path $dir 'run.ps1'
        [IO.File]::WriteAllText($runnerPath, $runner, $Utf8Bom)

        $startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }
        $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
            CommandLine               = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$runnerPath`""
            CurrentDirectory          = (Get-Location).Path
            ProcessStartupInformation = $startup
        }
        if ($r.ReturnValue -ne 0) { throw "起動に失敗した（Win32_Process.Create の戻り値 $($r.ReturnValue)）" }
        Set-Content -LiteralPath (Join-Path $dir 'pid') -Value $r.ProcessId -Encoding ascii
        Write-Output "起動した: $jobId（pid=$($r.ProcessId)）"
        Write-Output "状態: powershell -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" status -Id $jobId"
    }
    'status' {
        if ($Id) { $dirs = @(Get-Item -LiteralPath (Get-JobDir $Id)) }
        elseif (Test-Path -LiteralPath $Root) { $dirs = @(Get-ChildItem -LiteralPath $Root -Directory | Sort-Object Name) }
        else { $dirs = @() }
        if ($dirs.Count -eq 0) { Write-Output 'ジョブは無い'; break }
        foreach ($d in $dirs) { Write-Output ('{0}  {1}' -f $d.Name, (Get-JobState $d.FullName)) }
    }
    'log' {
        if (-not $Id) { throw 'log には -Id が必要' }
        $log = Join-Path (Get-JobDir $Id) 'output.log'
        if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log -Tail $Lines -Encoding UTF8 } else { Write-Output '（出力はまだ無い）' }
    }
    'claim' {
        if (-not $Id) { throw 'claim には -Id が必要' }
        $dir = Get-JobDir $Id
        if (-not (Test-Path -LiteralPath (Join-Path $dir 'exit.code'))) { throw "まだ完了していない: $Id" }
        Set-Content -LiteralPath (Join-Path $dir 'collected') -Value (Get-Date -Format o) -Encoding ascii
        Write-Output "報告済みにした: $Id"
    }
}
