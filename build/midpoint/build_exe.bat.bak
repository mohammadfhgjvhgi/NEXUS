@echo off
title NEXUS.exe build (MIDPOINT)
cd /d M:\NEXUS\build\midpoint
echo ==================================================
echo  NEXUS.exe build - MIDPOINT (onefile, console)
echo ==================================================
where py >nul 2>nul
if not %errorlevel%==0 (
  echo [x] py launcher not found - install Python 3.14 first.
  pause
  exit /b 1
)
py -3.14 -m pip install --upgrade pyinstaller || goto :err
py -3.14 -m PyInstaller --noconfirm --clean NEXUS.exe.spec || goto :err
echo.
echo [+] done: M:\NEXUS\build\midpoint\dist\NEXUS.exe
echo    first real run: dist\NEXUS.exe --check
pause
exit /b 0
:err
echo [x] build failed (honest output above).
pause
exit /b 1
