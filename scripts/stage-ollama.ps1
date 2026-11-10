$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-Location (Split-Path $PSScriptRoot -Parent)
if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'Stage the Windows runtime on Windows.' }
$headers = @{ 'User-Agent' = 'PM-Copilot-packager'; Accept = 'application/vnd.github+json' }
if ($env:GH_TOKEN) { $headers.Authorization = 'Bearer ' + $env:GH_TOKEN }
$release = Invoke-RestMethod -Uri 'https://api.github.com/repos/ollama/ollama/releases/latest' -Headers $headers
if ($release.draft -or $release.prerelease -or $release.tag_name -notmatch '^v[0-9]+\.[0-9]+\.[0-9]+$') { throw 'A stable official Ollama release is required.' }
$asset = @($release.assets | Where-Object { $_.name -eq 'ollama-windows-amd64.zip' })
if ($asset.Count -ne 1 -or $asset[0].digest -notmatch '^sha256:[a-fA-F0-9]{64}$') { throw 'Official x64 archive and published SHA-256 digest are required.' }
$expected = $asset[0].digest.Substring(7).ToLowerInvariant()
$url = 'https://github.com/ollama/ollama/releases/download/' + $release.tag_name + '/ollama-windows-amd64.zip'
if ($asset[0].browser_download_url -ne $url) { throw 'Unexpected runtime archive origin.' }
$archive = Join-Path $PWD 'build/runtime/ollama-windows-amd64.zip'
$stage = Join-Path $PWD 'build/runtime/ollama.installing'
$target = Join-Path $PWD 'build/runtime/ollama'
New-Item -ItemType Directory -Force (Split-Path $archive -Parent) | Out-Null
if (-not (Test-Path $archive) -or (Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
    Invoke-WebRequest -Uri $url -OutFile $archive -UseBasicParsing
}
if ((Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Ollama archive checksum mismatch.' }
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory $stage | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($archive)
try {
    foreach ($entry in $zip.Entries) {
        $destination = [IO.Path]::GetFullPath((Join-Path $stage $entry.FullName))
        if (-not $destination.StartsWith($stage + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe archive entry.' }
        if ((($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) { throw 'Runtime archive symlinks are unsupported.' }
    }
} finally { $zip.Dispose() }
[IO.Compression.ZipFile]::ExtractToDirectory($archive, $stage)
if (-not (Test-Path (Join-Path $stage 'ollama.exe'))) { throw 'Runtime executable missing from official archive.' }
Invoke-WebRequest -Uri ('https://raw.githubusercontent.com/ollama/ollama/' + $release.tag_name + '/LICENSE') -OutFile (Join-Path $stage 'OLLAMA-LICENSE.txt') -UseBasicParsing
@{ schema = 1; repository = 'ollama/ollama'; version = $release.tag_name; archive_url = $url; archive_sha256 = $expected; executable_sha256 = (Get-FileHash (Join-Path $stage 'ollama.exe') -Algorithm SHA256).Hash.ToLowerInvariant(); model_weights_included = $false } | ConvertTo-Json | Set-Content -Encoding ascii (Join-Path $stage 'installation.json')
if (Test-Path $target) { Remove-Item $target -Recurse -Force }
Move-Item $stage $target
Write-Host ('Staged verified official Ollama runtime ' + $release.tag_name)
