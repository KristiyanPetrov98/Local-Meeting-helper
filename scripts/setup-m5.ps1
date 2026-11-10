$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" } }
& .\scripts\setup-m4.ps1
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
dotnet restore services/screen-windows --locked-mode -r win-x64; Check-Exit
dotnet publish services/screen-windows -c Release -r win-x64 --self-contained false --no-restore; Check-Exit
Write-Host 'M5 built. Complete the existing M3 setup for live audio. Use start-ollama.ps1 for loopback inference with parallelism 1.'
Write-Host 'WGC, Google Meet sharing exclusion and RTX 4080 concurrency still require the tests in docs/milestone-5.md.'
