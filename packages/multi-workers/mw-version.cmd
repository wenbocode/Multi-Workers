@echo off
setlocal DisableDelayedExpansion
python -B "%~dp0mw_version.py" %*
exit /b %errorlevel%
