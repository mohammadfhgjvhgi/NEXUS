@echo off
title NEXUS C-AUTOPILOT - move-only disk relief
cd /d M:\NEXUS\tools\c_relief
echo ==================================================
echo  NEXUS C-AUTOPILOT  (move only, NEVER delete)
echo  Frees C: by moving data to M: + live junctions
echo ==================================================
echo.
where python >nul 2>nul
if %errorlevel%==0 (
  python autopilot.py
) else (
  py -3 autopilot.py
)
echo.
echo ===== finished - status file: =====
echo M:\NEXUS\tools\c_relief\results\autopilot_status.json
echo (safe to close this window or re-run at any time)
pause
