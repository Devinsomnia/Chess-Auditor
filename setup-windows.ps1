# ============================================================================
# chess-auditor one-click setup for Windows
#
# Installs everything the app needs, then builds dist\ChessAuditor.exe:
#   1. Miniconda  (Python environment manager)        - via winget
#   2. Stockfish  (the chess engine)                  - via winget
#   3. The `chessauditor` Python environment          - from environment.yml
#   4. Points config.yaml at the installed Stockfish
#   5. Builds the one-click desktop app (dist\ChessAuditor.exe)
#
# Run it by double-clicking setup-windows.bat, or from PowerShell:
#   powershell -ExecutionPolicy Bypass -File setup-windows.ps1
#
# Safe to re-run: every step is skipped if it's already done.
# Use -SkipBuild to do everything except the (slow) exe build.
# ============================================================================
param(
    [switch]$SkipBuild
)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Fail($msg) { Write-Host "    ERROR: $msg" -ForegroundColor Red; exit 1 }

# --- 0. winget (needed to install Miniconda / Stockfish) --------------------
$winget = Get-Command winget -ErrorAction SilentlyContinue
if (-not $winget) {
    Write-Host "winget (Windows Package Manager) was not found." -ForegroundColor Yellow
    Write-Host "It ships with Windows 10/11 as 'App Installer'. Install/update it from the" -ForegroundColor Yellow
    Write-Host "Microsoft Store (search 'App Installer'), then run this script again." -ForegroundColor Yellow
    exit 1
}

# --- 1. Miniconda ------------------------------------------------------------
Step "Checking for conda (Miniconda/Anaconda)..."
$condaCandidates = @(
    "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
    "$env:USERPROFILE\anaconda3\Scripts\conda.exe",
    "$env:LOCALAPPDATA\miniconda3\Scripts\conda.exe",
    "$env:ProgramData\miniconda3\Scripts\conda.exe"
)
$conda = $condaCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $conda) {
    $cmd = Get-Command conda -ErrorAction SilentlyContinue
    if ($cmd) { $conda = $cmd.Source }
}
if (-not $conda) {
    Step "Installing Miniconda (this downloads ~80 MB)..."
    winget install --id Anaconda.Miniconda3 --accept-package-agreements --accept-source-agreements --silent
    $conda = $condaCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $conda) { Fail "Miniconda installed but conda.exe was not found. Open a NEW terminal and re-run this script." }
}
Ok "conda: $conda"

# --- 2. Stockfish ------------------------------------------------------------
Step "Checking for Stockfish..."
function Find-Stockfish {
    $cmd = Get-Command stockfish -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $pkgDirs = @(
        "$env:LOCALAPPDATA\Microsoft\WinGet\Packages",
        "$env:ProgramFiles\WinGet\Packages"
    )
    foreach ($d in $pkgDirs) {
        if (Test-Path $d) {
            $hit = Get-ChildItem $d -Recurse -Filter "stockfish*.exe" -ErrorAction SilentlyContinue |
                   Select-Object -First 1
            if ($hit) { return $hit.FullName }
        }
    }
    return $null
}
$stockfish = Find-Stockfish
if (-not $stockfish) {
    Step "Installing Stockfish..."
    winget install --id Stockfish.Stockfish --accept-package-agreements --accept-source-agreements --silent
    $stockfish = Find-Stockfish
    if (-not $stockfish) { Fail "Stockfish installed but its exe was not found. Install it manually from https://stockfishchess.org/download/ and put its path in config.yaml under engine.path." }
}
Ok "stockfish: $stockfish"

# --- 3. Python environment ---------------------------------------------------
Step "Creating/updating the 'chessauditor' Python environment (first run takes a few minutes)..."
& $conda env update -n chessauditor -f (Join-Path $root "environment.yml") --prune
if ($LASTEXITCODE -ne 0) { Fail "conda env update failed (see output above)." }
Ok "environment ready"

# --- 4. Point config.yaml at Stockfish ---------------------------------------
Step "Writing the Stockfish path into config.yaml..."
$cfgPath = Join-Path $root "config.yaml"
$cfg = Get-Content $cfgPath -Raw -Encoding UTF8
# In a .NET regex replacement only '$' is special - escape it; backslashes are fine.
$repl = $stockfish.Replace('$', '$$')
$cfg = $cfg -replace '(?m)^(\s*path:\s*).*$', "`${1}$repl"
Set-Content $cfgPath $cfg -Encoding UTF8 -NoNewline
Ok "config.yaml -> engine.path = $stockfish"

# --- 5. Build the desktop app -------------------------------------------------
if ($SkipBuild) {
    Write-Host "`nSkipping exe build (-SkipBuild). Run .\build-exe.ps1 later to create dist\ChessAuditor.exe," -ForegroundColor Yellow
    Write-Host "or use .\run-live.ps1 / .\run-demo.ps1 to run from source." -ForegroundColor Yellow
} else {
    Step "Building dist\ChessAuditor.exe (takes a minute or two)..."
    & (Join-Path $root "build-exe.ps1")
    if ($LASTEXITCODE -ne 0) { Fail "exe build failed (see output above)." }
}

Write-Host ""
Write-Host "=================== SETUP COMPLETE ===================" -ForegroundColor Green
Write-Host " Double-click  dist\Chess Auditor (Desktop).lnk  to start the app." -ForegroundColor Green
Write-Host " Next: install the browser userscript (see README, step 2)." -ForegroundColor Green
Write-Host "=======================================================" -ForegroundColor Green
