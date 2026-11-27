# detect-tools.ps1 — 外部コマンドの所在・版・文字コード環境を調べ、~/.claude/tool-environment.json に書く（Windows）
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File detect-tools.ps1 [追加のコマンド名...]
#
# 既存の json に "notes" があれば引き継ぐ（手で書いた補足を消さない）。
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Extra)
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }   # Git Bash から呼ばれても日本語が化けないように
$OutFile = if ($env:TOOL_ENV_OUT) { $env:TOOL_ENV_OUT } else { Join-Path $HOME '.claude\tool-environment.json' }

$tools = @('git', 'gh', 'python', 'python3', 'py', 'uv', 'node', 'npm', 'npx', 'bun', 'deno', 'pwsh', 'powershell',
    'bash', 'wsl', 'winget', 'scoop', 'choco', 'mise', 'podman', 'docker', 'docker-compose', 'pandoc', 'pdftotext',
    'jq', 'rg', 'curl', 'cargo', 'rustc', 'go', 'java', 'dotnet', 'code', 'dot', 'rtk') + @($Extra | Where-Object { $_ })
$versionArgs = @{ 'go' = 'version'; 'java' = '-version'; 'dotnet' = '--version'; 'wsl' = '--status'; 'dot' = '-V' }

function Get-FirstLine([string]$exe, [string]$arg) {
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $exe; $psi.Arguments = $arg
        $psi.UseShellExecute = $false; $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        $p = [System.Diagnostics.Process]::Start($psi)
        $outTask = $p.StandardOutput.ReadToEndAsync(); $errTask = $p.StandardError.ReadToEndAsync()
        if (-not $p.WaitForExit(5000)) { try { $p.Kill() } catch {}; return '(5 秒以内に応答なし)' }
        $text = ($outTask.Result + "`n" + $errTask.Result) -replace "`0", ''
        return (($text -split "`r?`n") | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
    } catch { return "(取得失敗: $($_.Exception.Message))" }
}

$result = [ordered]@{}
foreach ($t in ($tools | Select-Object -Unique)) {
    $cmd = Get-Command $t -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd) { $result[$t] = [ordered]@{ found = $false }; continue }
    $entry = [ordered]@{ found = $true; path = $cmd.Source }
    if ($t -match '^python3?$' -and $cmd.Source -like '*\WindowsApps\*') {
        # WindowsApps の python.exe は、Store 版 Python の実行エイリアス（実体）か、未導入時の案内用スタブのどちらか。
        # スタブは --version に版を返さない（Store への案内を出して終わる）ので、版が返るかで見分ける
        $ver = Get-FirstLine $cmd.Source '--version'
        if ($ver -match '^Python \d') {
            $entry.version = $ver
            $entry.note = 'Microsoft Store 版 Python（WindowsApps の実行エイリアス経由。実体）'
        } else {
            $entry.note = 'Microsoft Store の案内用スタブ。実体の Python ではない'
        }
    } elseif ($t -eq 'powershell') {
        $entry.version = Get-FirstLine $cmd.Source '-NoProfile -Command $PSVersionTable.PSVersion.ToString()'
    } elseif ($t -eq 'pwsh') {
        $entry.version = Get-FirstLine $cmd.Source '-NoProfile -Command $PSVersionTable.PSVersion.ToString()'
    } else {
        $arg = if ($versionArgs.ContainsKey($t)) { $versionArgs[$t] } else { '--version' }
        $entry.version = Get-FirstLine $cmd.Source $arg
    }
    $result[$t] = $entry
}

# Git Bash（Claude Code の Bash ツールが使う）
$gitBash = $null
if ($result['git'].found) {
    # git.exe は Git\cmd\ にも Git\mingw64\bin\ にもありうるので、上へたどって Git\bin\bash.exe を探す
    $dir = Split-Path -Parent $result['git'].path
    for ($i = 0; $i -lt 4 -and $dir -and -not $gitBash; $i++) {
        $candidate = Join-Path $dir 'bin\bash.exe'
        if (Test-Path -LiteralPath $candidate) { $gitBash = $candidate }
        $dir = Split-Path -Parent $dir
    }
}

$acp = $null
try { $acp = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Nls\CodePage' -ErrorAction Stop).ACP } catch {}

$notes = $null
if (Test-Path -LiteralPath $OutFile) {
    try { $notes = (Get-Content -Raw -Encoding UTF8 -LiteralPath $OutFile | ConvertFrom-Json).notes } catch {}
}

$doc = [ordered]@{
    generated = (Get-Date -Format o)
    os        = [ordered]@{ platform = 'windows'; version = [Environment]::OSVersion.VersionString }
    encoding  = [ordered]@{
        ansi_code_page    = $acp
        console_code_page = [Console]::OutputEncoding.CodePage
        note              = 'ANSI コードページが 932 なら、BOM の無い UTF-8 の .ps1 は Windows PowerShell 5.1 で文字化けする'
    }
    git_bash  = $gitBash
    tools     = $result
    notes     = $notes
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutFile) | Out-Null
[IO.File]::WriteAllText($OutFile, ($doc | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding($false)))

$found = @($result.Keys | Where-Object { $result[$_].found })
$missing = @($result.Keys | Where-Object { -not $result[$_].found })
Write-Output "書き込んだ: $OutFile"
Write-Output "見つかった: $($found.Count) 件 / 見つからない: $($missing.Count) 件（$($missing -join ', ')）"
foreach ($k in $found) { if ($result[$k].note) { Write-Output "注意 ${k}: $($result[$k].note)" } }
