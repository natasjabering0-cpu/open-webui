@echo off
set ROOT_DIR=%~dp0
if exist "%ROOT_DIR%venv\Scripts\pythonw.exe" (
  start "" "%ROOT_DIR%venv\Scripts\pythonw.exe" "%ROOT_DIR%tray_assistant.py"
) else (
  start "" pyw "%ROOT_DIR%tray_assistant.py"
)
