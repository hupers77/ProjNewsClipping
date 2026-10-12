@echo off
rem Double-click to build the Windows installer (see build_windows.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1"
echo.
pause
