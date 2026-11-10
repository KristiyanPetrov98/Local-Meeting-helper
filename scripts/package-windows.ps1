$ErrorActionPreference = 'Stop'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'Build the Windows installer on Windows x64; cross-platform backend binaries are not interchangeable.' }
Set-Location (Split-Path $PSScriptRoot -Parent)
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" } }
if (-not (Test-Path '.packaging/venv/Scripts/python.exe')) { py -3.12 -m venv .packaging/venv; Check-Exit }
$buildPython = Join-Path $PWD '.packaging/venv/Scripts/python.exe'
& $buildPython -m pip install --require-hashes -r services/api/requirements-assistance.lock -r services/api/requirements-asr.lock -r services/api/requirements-diarization-windows.lock -r services/api/requirements-packaging.lock; Check-Exit
& $buildPython -m pip check; Check-Exit
npm ci --ignore-scripts; Check-Exit
node node_modules/electron/install.js; Check-Exit
npm run typecheck; Check-Exit
npm run build; Check-Exit
& .\scripts\stage-ollama.ps1
& .\scripts\stage-ffmpeg.ps1
& .\scripts\stage-vcredist.ps1
$env:PATH = (Join-Path $PWD 'build/runtime/ffmpeg/bin') + [IO.Path]::PathSeparator + $env:PATH
dotnet restore services/capture-windows --locked-mode -r win-x64 -p:SelfContained=true; Check-Exit
dotnet publish services/capture-windows -c Release -r win-x64 --self-contained true --no-restore -o build/helpers/audio; Check-Exit
dotnet restore services/screen-windows --locked-mode -r win-x64 -p:SelfContained=true; Check-Exit
dotnet publish services/screen-windows -c Release -r win-x64 --self-contained true --no-restore -o build/helpers/screen; Check-Exit
& $buildPython -m PyInstaller --noconfirm --clean --distpath build/backend --workpath build/pyinstaller packaging/backend.spec; Check-Exit
& $buildPython scripts/collect-notices.py; Check-Exit
node scripts/smoke-engine.mjs; Check-Exit
& $buildPython scripts/smoke-bundle.py --backend build/backend/pm-copilot-api/pm-copilot-api.exe --web apps/web/dist --output build/notices/backend-smoke.json --require-diarization; Check-Exit
npm run package:win; Check-Exit
Get-ChildItem release/*Setup.exe | ForEach-Object { (Get-FileHash $_.FullName -Algorithm SHA256).Hash + '  ' + $_.Name } | Set-Content -Encoding ascii release/SHA256SUMS.txt
$manifest = Get-Content build/notices/runtime-manifest.json -Raw | ConvertFrom-Json
$installer = Get-ChildItem release/*Setup.exe | Sort-Object LastWriteTime -Descending | Select-Object -First 1
@{ schema = 1; status = 'passed'; platform = 'win32'; source_digest = $manifest.source_digest; full_model_runtime = $manifest.fullModelRuntime; bundled_smoke_passed = $true; installer_sha256 = (Get-FileHash $installer.FullName -Algorithm SHA256).Hash.ToLowerInvariant(); clean_machine_install_verified = $false; release_qualified = $false } | ConvertTo-Json | Set-Content -Encoding ascii build/notices/windows-build.json
Write-Host 'Unsigned per-user installer with managed local AI engine built. Model preparation runs inside the app. Complete clean-machine, audio and GPU qualification before release.'
