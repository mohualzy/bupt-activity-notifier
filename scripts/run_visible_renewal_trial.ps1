# One-time, human-supervised JWT renewal trial.
# Only run manually in YOUR interactive PowerShell. Never scheduled.
# This does not modify the stable project, .env, or the activity-dedup ledger.
$ErrorActionPreference = 'Stop'
$lab = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$stable = Join-Path (Split-Path $lab -Parent) 'bupt-activity-notifier'
$privateEnv = Join-Path $stable '.env'
if (!(Test-Path -LiteralPath $privateEnv)) {
    Write-Output 'Stable project private configuration was not found; nothing attempted.'
    exit 2
}
if ([Console]::IsInputRedirected -or [Console]::IsOutputRedirected) {
    Write-Output 'Visible re-login must be run in your own interactive PowerShell terminal.'
    exit 2
}

$previousPythonPath = [Environment]::GetEnvironmentVariable('PYTHONPATH', 'Process')
$previousStableRoot = [Environment]::GetEnvironmentVariable('BUPT_ACTIVITY_STABLE_ROOT', 'Process')
$previousLabRoot = [Environment]::GetEnvironmentVariable('BUPT_RENEW_LAB_ROOT', 'Process')
try {
    $env:PYTHONPATH = (Join-Path $lab 'src') + [IO.Path]::PathSeparator + $previousPythonPath
    $env:BUPT_ACTIVITY_STABLE_ROOT = $stable
    $env:BUPT_RENEW_LAB_ROOT = $lab
    Push-Location -LiteralPath $stable
    try {
        # No passwords, tokens, cookies, or auth tickets are command arguments.
        # The Python code itself loads the ignored .env in memory, then invokes
        # the isolated experiment's human-supervised browser login entrypoint.
        $python = @'
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

stable = Path(os.environ["BUPT_ACTIVITY_STABLE_ROOT"]).resolve()
lab = Path(os.environ["BUPT_RENEW_LAB_ROOT"]).resolve()
sys.path.insert(0, str(lab / "src"))
import bupt_activity_notifier
if not Path(bupt_activity_notifier.__file__).resolve().is_relative_to(lab / "src"):
    print("The experimental module was not loaded; no sign-in attempted.")
    sys.exit(2)
load_dotenv(dotenv_path=stable / ".env", override=True)
from bupt_activity_notifier.cli import main
sys.exit(main(["--renew-now", "--headed", "--state", str(stable / ".state" / "seen.json")]))
'@
        & python -c $python
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
} finally {
    [Environment]::SetEnvironmentVariable('PYTHONPATH', $previousPythonPath, 'Process')
    [Environment]::SetEnvironmentVariable('BUPT_ACTIVITY_STABLE_ROOT', $previousStableRoot, 'Process')
    [Environment]::SetEnvironmentVariable('BUPT_RENEW_LAB_ROOT', $previousLabRoot, 'Process')
}
if ($exitCode -eq 0) {
    Write-Output 'Pilot passed. The newly verified JWT is stored in Windows Credential Manager.'
    Write-Output 'Automatic renewal remains OFF. Do not enable without a separate decision.'
} else {
    Write-Output 'Pilot did not pass. Stable watcher and private Token remain unchanged.'
}
exit $exitCode
