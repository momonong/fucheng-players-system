@echo off
setlocal
cd /d "%~dp0..\.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0check-and-send.ps1" %*
set "report_exit=%ERRORLEVEL%"
echo.
echo Report files stay in the data folder. Exit code: %report_exit%
pause
exit /b %report_exit%
