# Shared LGPL FFmpeg libraries for the bundled TorchCodec/diarization runtime.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-Location (Split-Path $PSScriptRoot -Parent)
if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'Stage Windows libraries on Windows.' }
$headers = @{ 'User-Agent' = 'PM-Copilot-packager'; Accept = 'application/vnd.github+json' }
if ($env:GH_TOKEN) { $headers.Authorization = 'Bearer ' + $env:GH_TOKEN }
$release = Invoke-RestMethod -Uri 'https://api.github.com/repos/FFmpeg-Builds/FFmpeg-Builds/releases/latest' -Headers $headers
$asset = $release.assets | Where-Object { $_.name -match '^ffmpeg-n(7|8)\.[0-9.]+-latest-win64-lgpl-shared-[0-9.]+\.zip$' } | Sort-Object name -Descending | Select-Object -First 1
if (-not $asset -or $asset.digest -notmatch '^sha256:[a-fA-F0-9]{64}$') { throw 'A published-digest Windows LGPL shared FFmpeg 7/8 build is required.' }
$url = 'https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/download/' + $release.tag_name + '/' + $asset.name
if ($asset.browser_download_url -ne $url) { throw 'Unexpected FFmpeg archive origin.' }
$expected = $asset.digest.Substring(7).ToLowerInvariant()
$archive = Join-Path $PWD 'build/runtime/ffmpeg.zip'
$stage = Join-Path $PWD 'build/runtime/ffmpeg.installing'
$target = Join-Path $PWD 'build/runtime/ffmpeg'
New-Item -ItemType Directory -Force (Split-Path $archive -Parent) | Out-Null
if (-not (Test-Path $archive) -or (Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { Invoke-WebRequest -Uri $url -OutFile $archive -UseBasicParsing }
if ((Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'FFmpeg archive checksum mismatch.' }
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory $stage | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($archive)
try {
    foreach ($entry in $zip.Entries) {
        $destination = [IO.Path]::GetFullPath((Join-Path $stage $entry.FullName))
        if (-not $destination.StartsWith($stage + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe FFmpeg archive entry.' }
        if ((($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) { throw 'FFmpeg archive symlinks are unsupported.' }
    }
} finally { $zip.Dispose() }
[IO.Compression.ZipFile]::ExtractToDirectory($archive, $stage)
$codec = @(Get-ChildItem $stage -Recurse -Filter 'avcodec-*.dll')
if ($codec.Count -ne 1 -or $codec[0].Directory.Name -ne 'bin') { throw 'Shared FFmpeg codec DLL inventory is invalid.' }
$root = $codec[0].Directory.Parent.FullName
if (-not (Get-ChildItem $root -Recurse -File | Where-Object { $_.Name -match '^(LICENSE|COPYING)' })) { throw 'FFmpeg license texts must accompany the libraries.' }
@{ schema = 1; repository = 'FFmpeg-Builds/FFmpeg-Builds'; release = $release.tag_name; asset = $asset.name; archive_sha256 = $expected; source_and_build_instructions = 'https://github.com/FFmpeg-Builds/FFmpeg-Builds'; source_archive_url = $url; variant = 'lgpl-shared' } | ConvertTo-Json | Set-Content -Encoding ascii (Join-Path $root 'installation.json')
if (Test-Path $target) { Remove-Item $target -Recurse -Force }
Move-Item $root $target
Remove-Item $stage -Recurse -Force
$build = & (Join-Path $target 'bin/ffmpeg.exe') -version 2>&1
if ($LASTEXITCODE -ne 0 -or ($build -join "`n") -match '--enable-(gpl|nonfree)\b') { throw 'The staged LGPL shared FFmpeg build could not pass its version/configuration check.' }
$build | Set-Content -Encoding utf8 (Join-Path $target 'BUILD-CONFIGURATION.txt')
Write-Host ('Staged shared FFmpeg runtime ' + $asset.name)
