# Launch the chess-auditor DEMO under the `chessauditor` conda env.
# Cycles sample positions through the overlay (no browser/game needed).
# Open http://localhost:8765/ to see the overlay.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root
$py = & "$PSScriptRoot\_find-conda-python.ps1"
Write-Host "chess-auditor demo -> http://localhost:8765/  (Ctrl+C to stop)" -ForegroundColor Green
& $py (Join-Path $root "demo.py")
