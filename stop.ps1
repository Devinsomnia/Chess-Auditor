# Stop any running chess-auditor python processes (demo or live).
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*chess_auditor*' -or $_.CommandLine -like '*demo.py*' } |
  ForEach-Object {
    Write-Host "Stopping PID $($_.ProcessId)" -ForegroundColor Yellow
    Stop-Process -Id $_.ProcessId -Force
  }
Write-Host "Done." -ForegroundColor Green
