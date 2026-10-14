# Install a per-user, no-console Task Scheduler watcher.
# Run in PowerShell 7: pwsh -NoProfile -File .\scripts\install_windows_task.ps1

$ErrorActionPreference = 'Stop'
$taskName = 'BUPT-SecondClass-Activity-Watcher'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$scriptPath = Join-Path $PSScriptRoot 'windows_watch.py'
$statePath = Join-Path $root '.state\seen.json'
$envPath = Join-Path $root '.env'

if (-not (Test-Path $envPath)) {
    throw 'Missing private .env; configure authentication and notification locally.'
}
if (-not (Test-Path $statePath)) {
    throw 'Missing initial seen.json baseline. First run --once to avoid historical notifications.'
}

$pythonExe = (& python -c 'import sys; print(sys.executable)').Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $pythonExe)) {
    throw 'Unable to locate a working Python interpreter.'
}
$pythonwExe = Join-Path (Split-Path $pythonExe -Parent) 'pythonw.exe'
if (-not (Test-Path $pythonwExe)) {
    throw 'pythonw.exe missing; cannot run a windowless task.'
}

$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $pythonwExe -Argument ('"' + $scriptPath + '"') -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Read-only BUPT Second Classroom watcher every 300 seconds; credentials stored only in local ignored .env' -Force | Out-Null

Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 2
$task = Get-ScheduledTask -TaskName $taskName
$info = Get-ScheduledTaskInfo -TaskName $taskName
Write-Output ('TASK_NAME=' + $taskName)
Write-Output ('TASK_STATE=' + $task.State)
Write-Output ('TASK_LAST_RESULT=' + $info.LastTaskResult)
Write-Output ('TASK_PRINCIPAL=' + $task.Principal.UserId)
Write-Output ('TASK_PYTHONW_EXISTS=' + (Test-Path $pythonwExe))
Write-Output 'TASK_INSTALL_FINISHED=true'
