@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
python -m order_profit.desktop
if errorlevel 1 (
  echo.
  echo 启动失败。请确认已安装 Python 3.11-3.14 及项目依赖。
  echo 安装命令: python -m pip install -e "."
  pause
)
endlocal
