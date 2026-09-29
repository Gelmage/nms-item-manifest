@echo off
REM Double-click to start the NMS Item Manifest.
REM Windows ships no Python, so check for it before blaming the tool.

setlocal
cd /d "%~dp0"

set PY=
where py >nul 2>&1 && set PY=py
if "%PY%"=="" (where python >nul 2>&1 && set PY=python)

if "%PY%"=="" (
    echo.
    echo   Python is not installed, and this tool needs it.
    echo.
    echo   Get it from   https://www.python.org/downloads/
    echo   On the first screen of the installer, tick
    echo   "Add python.exe to PATH" before pressing Install.
    echo.
    echo   Then double-click this file again.
    echo.
    pause
    exit /b 1
)

%PY% -c "import lz4" >nul 2>&1
if errorlevel 1 (
    echo Installing the one dependency ^(lz4^)...
    %PY% -m pip install --quiet lz4
    if errorlevel 1 (
        echo.
        echo   Could not install lz4. Try running:   %PY% -m pip install lz4
        echo.
        pause
        exit /b 1
    )
)

%PY% manifest.py %*
if errorlevel 1 pause
