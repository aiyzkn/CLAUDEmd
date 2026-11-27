# notify.ps1 — Notification フック: 許可待ち・入力待ちを Windows のトースト通知で知らせる
#
# stdin には Notification の JSON（message / title / notification_type など）が渡る。
# WinRT の ToastNotificationManager を使うため PowerShell 5.1（powershell.exe）で実行する（pwsh 7 では型を読めない）。
# 通知は Windows PowerShell の AppID で出すので、アクションセンターには「Windows PowerShell」として残る。
# fail-open 設計: 通知に失敗しても exit 0 とし、Claude Code の動作を妨げない。

try {
    $raw = ''
    if ([Console]::IsInputRedirected) {
        $reader = New-Object System.IO.StreamReader([Console]::OpenStandardInput(), [System.Text.Encoding]::UTF8)
        $raw = $reader.ReadToEnd()
    }
    $title = 'Claude Code'
    $message = '入力を待っています'
    if ($raw) {
        $ev = $raw | ConvertFrom-Json
        if ($ev.title) { $title = [string]$ev.title }
        if ($ev.message) { $message = [string]$ev.message }
        if ($ev.cwd) { $title = $title + ' — ' + (Split-Path -Leaf ([string]$ev.cwd)) }
    }

    [void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
    [void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]

    $esc = { param($s) [System.Security.SecurityElement]::Escape($s) }
    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml(('<toast><visual><binding template="ToastGeneric"><text>{0}</text><text>{1}</text></binding></visual></toast>' -f (& $esc $title), (& $esc $message)))

    $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show(
        [Windows.UI.Notifications.ToastNotification]::new($xml))
} catch {
    [Console]::Error.WriteLine("notify.ps1: $($_.Exception.Message)")
}
exit 0
