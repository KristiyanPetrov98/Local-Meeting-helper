$ErrorActionPreference = 'Stop'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" } }
if (-not (Test-Path '.venv/Scripts/python.exe')) { py -3.12 -m venv .venv; Check-Exit }
.\.venv\Scripts\python -m pip install --require-hashes -r services/api/requirements-asr.lock; Check-Exit
dotnet restore services/capture-windows --locked-mode -r win-x64; Check-Exit
dotnet publish services/capture-windows -c Release -r win-x64 --self-contained false --no-restore; Check-Exit
npm ci --ignore-scripts; Check-Exit
node node_modules/electron/install.js; Check-Exit
npm run build; Check-Exit
Write-Host 'Build complete. Install local model assets as documented in docs/milestone-3.md before enabling capture.'
