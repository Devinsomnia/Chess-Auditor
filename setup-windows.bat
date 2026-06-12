@echo off
rem One-click setup for chess-auditor. Just double-click this file.
rem It installs Miniconda + Stockfish (via winget), creates the Python
rem environment, configures the engine path, and builds ChessAuditor.exe.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-windows.ps1"
echo.
pause
