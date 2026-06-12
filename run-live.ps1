# Launch chess-auditor in LIVE mode under the `chessauditor` conda env.
# Receives positions from the browser userscript and serves the overlay.
# Open http://localhost:8765/ in a browser / OBS Browser source.
#
# Search time is set by movetime_ms in config.yaml (default 250 ms = snappy).
# Override here if you want, e.g. add:  --movetime 150  (faster)  or  --depth 18 (stronger).
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root
$env:PYTHONPATH = Join-Path $root "src"

$py = & "$PSScriptRoot\_find-conda-python.ps1"
Write-Host "chess-auditor live overlay -> http://localhost:8765/" -ForegroundColor Green
Write-Host "Add that URL as an OBS Browser source. Ctrl+C to stop." -ForegroundColor Gray
& $py -u -m chess_auditor.main --source post --color auto
