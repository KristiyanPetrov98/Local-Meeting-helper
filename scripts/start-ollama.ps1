$ErrorActionPreference = 'Stop'
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) { throw 'Install Ollama locally first.' }
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_HOST = '127.0.0.1:11434'
Write-Host 'Starting loopback-only Ollama with one parallel request. Quit an existing Ollama tray server first if the port is in use.'
ollama serve
if ($LASTEXITCODE -ne 0) { throw "Ollama exited with code $LASTEXITCODE" }
