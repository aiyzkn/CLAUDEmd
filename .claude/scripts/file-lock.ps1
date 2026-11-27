# file-lock.ps1 — ファイルを書き込み・削除・改名できない状態にする（Windows）
#
#   lock   <パス...>     ロックする（ディレクトリは配下のファイルをすべて対象にする）
#   unlock [<パス...>]   指定したファイルのロックを外す。省略するとすべて外す
#   status               ロック中のファイルを表示する
#
# 仕組み: 常駐プロセスが対象ファイルを「読み取り共有のみ」で開いたままにする。
# 開いている間、他のプロセス（エディタ・Claude Code を含む）は書き込み・削除・改名ができない。
# 読み取りはできる。常駐プロセスは WMI で起動するため、呼び出し元のセッションが終わっても残る。
# PC を再起動するとロックは外れる。
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet('lock', 'unlock', 'status')]
    [string]$Action,
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Paths
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }   # Git Bash から呼ばれても日本語が化けないように
$StateDir = Join-Path $env:LOCALAPPDATA 'claude-file-lock'
$ListFile = Join-Path $StateDir 'files.json'
$PidFile = Join-Path $StateDir 'holder.pid'
$StopFile = Join-Path $StateDir 'stop'
$HolderPs1 = Join-Path $StateDir 'holder.ps1'
$MaxFiles = 1000
$Utf8Bom = New-Object System.Text.UTF8Encoding($true)

function Get-Locked {
    if (-not (Test-Path -LiteralPath $ListFile)) { return @() }
    # 5.1 の ConvertFrom-Json は配列を 1 要素として返すので、ForEach-Object で展開する
    return @(Get-Content -Raw -Encoding UTF8 -LiteralPath $ListFile | ConvertFrom-Json | ForEach-Object { $_ })
}

function Get-HolderProcess {
    if (-not (Test-Path -LiteralPath $PidFile)) { return $null }
    $p = Get-Process -Id ([int](Get-Content -Raw -LiteralPath $PidFile).Trim()) -ErrorAction SilentlyContinue
    if ($p -and $p.ProcessName -match '^powershell') { return $p }
    return $null
}

function Expand-Targets([string[]]$items) {
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($i in $items) {
        if (-not (Test-Path -LiteralPath $i)) { throw "見つからない: $i" }
        $item = Get-Item -LiteralPath $i -Force
        if ($item.PSIsContainer) {
            Get-ChildItem -LiteralPath $item.FullName -File -Recurse -Force | ForEach-Object { $out.Add($_.FullName) }
        } else { $out.Add($item.FullName) }
    }
    return $out
}

function Stop-Holder {
    $p = Get-HolderProcess
    if (-not $p) { return }
    Set-Content -LiteralPath $StopFile -Value 'stop' -Encoding ascii
    if (-not $p.WaitForExit(5000)) { Stop-Process -Id $p.Id -Force }
    Remove-Item -LiteralPath $StopFile, $PidFile -Force -ErrorAction SilentlyContinue
}

function Start-Holder([string[]]$files) {
    New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
    [IO.File]::WriteAllText($ListFile, (ConvertTo-Json -InputObject @($files)), $Utf8Bom)
    if ($files.Count -eq 0) { Remove-Item -LiteralPath $ListFile -Force; return }
    $holder = @"
`$files = Get-Content -Raw -Encoding UTF8 -LiteralPath '$($ListFile -replace "'", "''")' | ConvertFrom-Json
`$handles = foreach (`$f in `$files) {
    try { [IO.File]::Open(`$f, 'Open', 'Read', 'Read') } catch { }
}
while (-not (Test-Path -LiteralPath '$($StopFile -replace "'", "''")')) { Start-Sleep -Seconds 1 }
foreach (`$h in `$handles) { `$h.Dispose() }
"@
    [IO.File]::WriteAllText($HolderPs1, $holder, $Utf8Bom)
    Remove-Item -LiteralPath $StopFile -Force -ErrorAction SilentlyContinue
    $startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }
    $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine               = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$HolderPs1`""
        ProcessStartupInformation = $startup
    }
    if ($r.ReturnValue -ne 0) { throw "常駐プロセスの起動に失敗した（戻り値 $($r.ReturnValue)）" }
    Set-Content -LiteralPath $PidFile -Value $r.ProcessId -Encoding ascii
    Start-Sleep -Milliseconds 1500   # ファイルを開き終えるのを待つ
}

function Test-Locked([string]$f) {
    try { $s = [IO.File]::Open($f, 'Open', 'ReadWrite', 'ReadWrite'); $s.Dispose(); return $false } catch { return $true }
}

switch ($Action) {
    'lock' {
        if (-not $Paths) { throw 'lock にはパスが必要' }
        $all = @(Get-Locked) + @(Expand-Targets $Paths) | Sort-Object -Unique
        if ($all.Count -gt $MaxFiles) { throw "対象が $($all.Count) 件ある。上限は $MaxFiles 件" }
        Stop-Holder
        Start-Holder $all
        $ng = @($all | Where-Object { -not (Test-Locked $_) })
        Write-Output "ロック中: $($all.Count - $ng.Count) 件"
        foreach ($f in $ng) { Write-Output "ロックできなかった（他のプロセスが開いている可能性）: $f" }
    }
    'unlock' {
        $current = @(Get-Locked)
        if ($Paths) {
            $remove = @(Expand-Targets $Paths)
            $rest = @($current | Where-Object { $remove -notcontains $_ })
        } else { $rest = @() }
        Stop-Holder
        Start-Holder $rest
        Write-Output "ロックを外した: $($current.Count - $rest.Count) 件 / 残り: $($rest.Count) 件"
    }
    'status' {
        $files = @(Get-Locked)
        $p = Get-HolderProcess
        if ($files.Count -eq 0 -or -not $p) {
            Write-Output 'ロック中のファイルは無い'
            if ($files.Count -gt 0) { Write-Output "（記録は $($files.Count) 件あるが常駐プロセスが動いていない。再起動などで外れた。lock をやり直すと戻る）" }
            break
        }
        Write-Output "ロック中: $($files.Count) 件（常駐プロセス pid=$($p.Id)）"
        $files | ForEach-Object { Write-Output "  $_" }
    }
}
