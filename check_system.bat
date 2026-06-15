@echo off
setlocal
cd /d "%~dp0"
echo [1/4] Backend health
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-RestMethod -Uri http://127.0.0.1:8000/health | ConvertTo-Json -Depth 4"
echo.
echo [2/4] Node
"C:\Program Files\nodejs\node.exe" --version
echo.
echo [3/4] npm
"C:\Program Files\nodejs\npm.cmd" --version
echo.
echo [4/4] Frontend build
cd frontend
"C:\Program Files\nodejs\npm.cmd" run build
