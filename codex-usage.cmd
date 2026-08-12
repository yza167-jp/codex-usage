@echo off
setlocal

where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  py -3 "%~dp0codex-usage" %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  python "%~dp0codex-usage" %*
  exit /b %ERRORLEVEL%
)

echo codex-usage: Python 3.9+ was not found. Install Python and ensure either "py" or "python" is available on PATH. 1>&2
exit /b 9009
