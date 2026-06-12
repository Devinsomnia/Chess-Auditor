# Resolves the python.exe of the `chessauditor` conda environment.
# Used by run-live.ps1 / run-demo.ps1 so they work without `conda activate`.
$envName = "chessauditor"
$candidates = @(
  "$env:USERPROFILE\miniconda3\envs\$envName\python.exe",
  "$env:USERPROFILE\anaconda3\envs\$envName\python.exe",
  "$env:LOCALAPPDATA\miniconda3\envs\$envName\python.exe",
  "$env:LOCALAPPDATA\Continuum\miniconda3\envs\$envName\python.exe"
)
$py = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $py) {
  Write-Error "Could not find the '$envName' conda env. Create it with:  conda env create -f environment.yml"
  exit 1
}
$py
