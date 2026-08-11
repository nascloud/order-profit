@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
set "PYTHON_EXE="
set "LOG_FILE=%TEMP%\order-profit-launch.log"

rem Prefer the project virtual environment.
if exist "%CD%\.venv\Scripts\python.exe" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"

rem Otherwise use the first python.exe available on PATH.
if not defined PYTHON_EXE (
  for /f "delims=" %%I in ('where python.exe 2^>nul') do (
    if not defined PYTHON_EXE set "PYTHON_EXE=%%I"
  )
)

if not defined PYTHON_EXE goto :NO_PYTHON

rem Validate imports before detaching from the console.
"%PYTHON_EXE%" -c "import tkinter,pandas,openpyxl,xlrd,order_profit.desktop" >"%LOG_FILE%" 2>&1
if errorlevel 1 goto :IMPORT_FAILED

for %%I in ("%PYTHON_EXE%") do set "PYTHONW_EXE=%%~dpIpythonw.exe"
if exist "%PYTHONW_EXE%" (
  start "" "%PYTHONW_EXE%" -m order_profit.desktop
) else (
  start "" /min "%PYTHON_EXE%" -m order_profit.desktop
)
exit /b 0

:NO_PYTHON
>"%LOG_FILE%" echo Python was not found. Install Python 3.11-3.14 and retry.
start "" notepad.exe "%LOG_FILE%"
exit /b 2

:IMPORT_FAILED
>>"%LOG_FILE%" echo.
>>"%LOG_FILE%" echo Install project dependencies with:
>>"%LOG_FILE%" echo "%PYTHON_EXE%" -m pip install -e "%CD%"
start "" notepad.exe "%LOG_FILE%"
exit /b 3
