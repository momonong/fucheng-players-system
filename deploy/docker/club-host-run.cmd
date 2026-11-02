@echo off
setlocal
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0deploy\docker\club-host-one-shot.ps1" %*
set "check_exit=%ERRORLEVEL%"
echo.
echo Fucheng host check finished. Exit code: %check_exit%
pause
exit /b %check_exit%
