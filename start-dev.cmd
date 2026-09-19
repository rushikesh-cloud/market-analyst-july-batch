@echo off
setlocal
pushd "%~dp0" || exit /b 1
call npm run dev
set "dev_exit_code=%errorlevel%"
popd
exit /b %dev_exit_code%
