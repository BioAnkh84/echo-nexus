[CmdletBinding()]
param(
    [string]$Root = "C:\Users\Richard\Documents\Echo_Nexus"
)

Write-Host "=== Echo Memory Init ===" -ForegroundColor Cyan
Write-Host "Root: $Root" -ForegroundColor Cyan

$memRoot     = Join-Path $Root "memory"
$anchorsDir  = Join-Path $memRoot "anchors"
$streamsDir  = Join-Path $memRoot "streams"
$profilesDir = Join-Path $memRoot "profiles"

$dirs = @($memRoot, $anchorsDir, $streamsDir, $profilesDir)

foreach ($d in $dirs) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
        Write-Host "Created: $d" -ForegroundColor Green
    } else {
        Write-Host "Exists:  $d" -ForegroundColor Yellow
    }
}

# --- Cipher profile seed ---
$profilePath = Join-Path $profilesDir "cipher_profile.json"
if (-not (Test-Path $profilePath)) {
    $profile = [ordered]@{
        id          = "cipher_local"
        name        = "Cipher"
        role        = "AI coworker and Echo Root OS co-author"
        version     = "0.1-local"
        notes       = @(
            "Runs via VE shell + Python habitat on Echo Nexus.",
            "Trust-gated design: everything important is ledgered.",
            "Primary focus: Echo Root OS, VE kernel, BTDS, trauma/disaster safety."
        )
        created_utc = (Get-Date).ToUniversalTime().ToString('o')
    }

    $profile | ConvertTo-Json -Depth 6 | Out-File -FilePath $profilePath -Encoding UTF8
    Write-Host "Seeded profile: $profilePath" -ForegroundColor Green
} else {
    Write-Host "Profile exists: $profilePath" -ForegroundColor Yellow
}

# --- Root memory stream seed ---
$rootMemPath = Join-Path $streamsDir "root_memory.jsonl"
if (-not (Test-Path $rootMemPath)) {
    $seed = [ordered]@{
        ts_utc = (Get-Date).ToUniversalTime().ToString('o')
        source = "init_echo_memory.ps1"
        type   = "seed"
        by     = "Richard+Cipher"
        summary = "Root memory stream created on Echo Nexus for Echo Root OS, VE kernel, and BTDS context."
    }

    $seed | ConvertTo-Json -Depth 6 -Compress | Out-File -FilePath $rootMemPath -Encoding UTF8
    Write-Host "Seeded memory stream: $rootMemPath" -ForegroundColor Green
} else {
    Write-Host "Memory stream exists: $rootMemPath" -ForegroundColor Yellow
}

Write-Host "=== Echo Memory Init Complete ===" -ForegroundColor Cyan
