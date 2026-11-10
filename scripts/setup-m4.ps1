$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" } }
if (-not (Test-Path '.venv/Scripts/python.exe')) { py -3.12 -m venv .venv; Check-Exit }
.\.venv\Scripts\python -m pip install --require-hashes -r services/api/requirements-assistance.lock; Check-Exit
.\.venv\Scripts\python -m pip check; Check-Exit
npm ci --ignore-scripts; Check-Exit
node node_modules/electron/install.js; Check-Exit
npm run build; Check-Exit
Write-Host 'M4 built. Install local Ollama and pull qwen3-vl:8b-instruct-q4_K_M. Set OLLAMA_NUM_PARALLEL=1 before starting Ollama.'
Write-Host 'For live audio, also run setup-m3.ps1 and install Whisper/Community-1 assets. See docs/milestone-4.md for the test procedure.'
