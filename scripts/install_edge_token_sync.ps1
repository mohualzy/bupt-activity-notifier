# Install one per-user Microsoft Edge native-messaging host.
# Does not install a browser extension, run a login, or edit private JWTs.
param([switch]$Uninstall)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$extensionDir = Join-Path $root 'edge_token_sync'
$extension = Get-Content -LiteralPath (Join-Path $extensionDir 'manifest.json') -Raw | ConvertFrom-Json
$keyBytes = [Convert]::FromBase64String([string]$extension.key)
$digest = [Security.Cryptography.SHA256]::HashData($keyBytes)
$alphabet = 'abcdefghijklmnop'
$extId = -join (0..15 | ForEach-Object { "$($alphabet[[int]($digest[$_] -shr 4)])$($alphabet[[int]($digest[$_] -band 15)])" })
if ($extId -ne 'mcohcjkicfoblidoolgbpladhehllpbb') { throw 'Unexpected extension public key / ID. No registration performed.' }

$hostName = 'com.mohualzy.bupt_token_sync'
$registryKey = 'HKCU\Software\Microsoft\Edge\NativeMessagingHosts\' + $hostName
$configRegistryKey = 'HKCU:\Software\mohualzy\BUPTActivityNotifier\EdgeSync'
$hostManifest = Join-Path $root '.state\edge_native_host_manifest.json'
$launcherExe = Join-Path $PSScriptRoot 'edge_native_host_launcher.exe'

if ($Uninstall) {
    & reg.exe DELETE $registryKey /f
    if (Test-Path $configRegistryKey) { Remove-Item -Path $configRegistryKey -Force }
    if (Test-Path -LiteralPath $hostManifest) { Remove-Item -LiteralPath $hostManifest -Force }
    Write-Output 'Edge native host unregistered. The activity watcher and stored JWT are unchanged.'
    exit 0
}
$pythonExe = (Get-Command python.exe -ErrorAction Stop).Source
if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) { throw 'Python executable not found.' }
$gcc = (Get-Command gcc.exe -ErrorAction Stop).Source

# Compile a small binary-pipe forwarding EXE from checked-in source.
& $gcc -O2 -Wall -Wextra -municode -mwindows (Join-Path $PSScriptRoot 'edge_native_host_launcher.c') -o $launcherExe -ladvapi32
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $launcherExe)) {
    throw 'Native host launcher compilation failed.'
}

# Native host only accessible to the precisely whitelisted Edge extension.
$nativeManifest = @{
    name = $hostName
    description = 'BUPT second-classroom student JWT sync (local only)'
    path = $launcherExe
    type = 'stdio'
    allowed_origins = @('chrome-extension://' + $extId + '/')
} | ConvertTo-Json -Depth 4
$stateDirectory = Join-Path $root '.state'
New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
[IO.File]::WriteAllText($hostManifest, $nativeManifest + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))

# User-local configuration only. No admin rights, network listener or passwords.
New-Item -Path $configRegistryKey -Force | Out-Null
New-ItemProperty -Path $configRegistryKey -Name PythonExecutable -Value $pythonExe -PropertyType String -Force | Out-Null

& reg.exe ADD $registryKey /ve /t REG_SZ /d $hostManifest /f | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Failed to register the Edge native-messaging host.' }
$registered = (Get-Item -LiteralPath ('Registry::HKEY_CURRENT_USER\Software\Microsoft\Edge\NativeMessagingHosts\' + $hostName)).GetValue('')
if ($registered -ne $hostManifest) { throw 'Native host registry check failed.' }

Write-Output 'NATIVE_HOST_REGISTERED=true'
Write-Output ('EXPECTED_EDGE_EXTENSION_ID=' + $extId)
Write-Output ('EDGE_EXTENSION_DIRECTORY=' + $extensionDir)
Write-Output 'NEXT_ACTION=Edge: edge://extensions > Developer mode > Load unpacked > choose the directory above.'
Write-Output 'The stable activity watcher, .env, tokens, and notification settings were NOT changed.'
