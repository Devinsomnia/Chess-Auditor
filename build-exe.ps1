# Build the one-click desktop app: dist\ChessAuditor.exe
# Uses the `chessauditor` conda env. Re-run this whenever you change the code.
# Note: PyInstaller logs to stderr, so we DON'T use Stop/redirects here — we
# check the exit code instead (PowerShell 5.1 treats native stderr as errors).
$ErrorActionPreference = "Continue"
$root = $PSScriptRoot
Set-Location $root

$py = & "$root\_find-conda-python.ps1"
$envRoot = Split-Path $py            # ...\envs\chessauditor
# Put conda's Library\bin on PATH so PyInstaller bundles the OpenSSL DLLs that
# Python's ssl module (pulled in by pywebview) needs at runtime.
$env:PATH = (Join-Path $envRoot "Library\bin") + ";" + $env:PATH

Write-Host "Building ChessAuditor.exe (this takes a minute or two)..." -ForegroundColor Cyan
& $py -m PyInstaller --noconfirm --clean --onefile --noconsole --name ChessAuditor `
  --paths src `
  --collect-submodules chess_auditor `
  --collect-all webview `
  --add-data "src/chess_auditor/overlay/index.html;chess_auditor/overlay" `
  app.py
if ($LASTEXITCODE -ne 0) { Write-Host "PyInstaller failed ($LASTEXITCODE)" -ForegroundColor Red; exit 1 }

# config.yaml must live next to the exe (the app reads it from there, and you
# can edit engine path / depth / movetime without rebuilding).
Copy-Item (Join-Path $root "config.yaml") (Join-Path $root "dist\config.yaml") -Force

# Create clickable shortcuts for each window style.
$dist = Join-Path $root "dist"
$exe = Join-Path $dist "ChessAuditor.exe"
$ws = New-Object -ComObject WScript.Shell
foreach ($m in @("Desktop","OBS")) {
  $lnk = $ws.CreateShortcut((Join-Path $dist "Chess Auditor ($m).lnk"))
  $lnk.TargetPath = $exe
  $lnk.Arguments = "--mode " + $m.ToLower()
  $lnk.WorkingDirectory = $dist
  $lnk.Save()
}

Write-Host ""
Write-Host "Done -> dist\ChessAuditor.exe  (config.yaml + shortcuts copied beside it)" -ForegroundColor Green
Write-Host "Double-click 'Chess Auditor (Desktop).lnk' or 'Chess Auditor (OBS).lnk'." -ForegroundColor Green
