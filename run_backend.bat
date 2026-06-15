@echo off
setlocal
cd /d "%~dp0"
set PYTHONPATH=.;.deps
set PYTHONIOENCODING=utf-8
C:\Python313\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
