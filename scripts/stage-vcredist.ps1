$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-Location (Split-Path $PSScriptRoot -Parent)
if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'Validate the Windows redistributable on Windows.' }
$target = Join-Path $PWD 'build/runtime/vcredist'
New-Item -ItemType Directory -Force $target | Out-Null
$file = Join-Path $target 'vc_redist.x64.exe'
Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile $file -UseBasicParsing
$signature = Get-AuthenticodeSignature -FilePath $file
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation(?:,|$)') { throw 'A valid Microsoft-signed Visual C++ redistributable is required.' }
@{ schema = 1; publisher = 'Microsoft Corporation'; signature_status = 'Valid'; source_url = 'https://aka.ms/vs/17/release/vc_redist.x64.exe'; sha256 = (Get-FileHash $file -Algorithm SHA256).Hash.ToLowerInvariant(); version = (Get-Item $file).VersionInfo.FileVersion } | ConvertTo-Json | Set-Content -Encoding ascii (Join-Path $target 'installation.json')
