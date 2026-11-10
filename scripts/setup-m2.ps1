$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" } }
if (-not (Test-Path '.venv/Scripts/python.exe')) { py -3.12 -m venv .venv; Check-Exit }
.\.venv\Scripts\python -m pip install --require-hashes -r services/api/requirements-documents.lock; Check-Exit
.\.venv\Scripts\python -m pip check; Check-Exit
.\.venv\Scripts\python -c "import sqlite3; db=sqlite3.connect(':memory:'); db.execute('CREATE VIRTUAL TABLE fts_check USING fts5(text)'); db.close()"; Check-Exit
npm ci --ignore-scripts; Check-Exit
node node_modules/electron/install.js; Check-Exit
npm run build; Check-Exit
Write-Host 'Document import and keyword search are installed. For semantic search, install Ollama and pull qwen3-embedding:0.6b. See docs/milestone-2.md.'
