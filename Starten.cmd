@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows_start.ps1" %*
set "scan2mesh_exit=%ERRORLEVEL%"
if not "%scan2mesh_exit%"=="0" (
  echo.
  echo Scan2Mesh konnte nicht erfolgreich beendet werden. Siehe Meldung oben.
)
if not defined SCAN2MESH_NO_PAUSE pause
exit /b %scan2mesh_exit%
