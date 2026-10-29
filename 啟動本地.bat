@echo off
setlocal

cd /d "%~dp0"
title Interior Design Video Studio - Local

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [ERROR] .venv\Scripts\python.exe was not found.
    echo Create the virtual environment and install requirements first:
    echo.
    echo py -3.12 -m venv .venv
    echo .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

if not exist ".tmp" mkdir ".tmp"
set "TEMP=%CD%\.tmp"
set "TMP=%TEMP%"

echo.
echo Starting the Interior Design Video Studio...
echo The browser will open at http://localhost:8501
echo Press Ctrl+C in this window, or close it, to stop the server.
echo.

".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.headless false --browser.serverAddress localhost
set "APP_EXIT_CODE=%ERRORLEVEL%"

if not "%APP_EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] Streamlit exited with code %APP_EXIT_CODE%.
    echo Keep the error message above for troubleshooting.
    pause
)

exit /b %APP_EXIT_CODE%
