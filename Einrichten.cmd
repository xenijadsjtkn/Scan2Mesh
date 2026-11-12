@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows_setup.ps1"
set "SCAN2MESH_SETUP_EXIT=%ERRORLEVEL%"
if "%SCAN2MESH_SETUP_EXIT%"=="3010" echo Nach dem Windows-Neustart Einrichten.cmd erneut oeffnen.
if "%SCAN2MESH_SETUP_EXIT%"=="0" echo Einrichtung abgeschlossen. Ab jetzt Starten.cmd oeffnen.
if not defined SCAN2MESH_NO_PAUSE pause
exit /b %SCAN2MESH_SETUP_EXIT%
