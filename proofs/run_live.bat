@echo off
rem §12.5 decision run — PATH extended post-install (the bridge env predates the install)
set "PATH=%PATH%;C:\Program Files\Tesseract-OCR"
where tesseract >nul 2>&1 || echo [WARN] tesseract still not on PATH
cd /d M:\NEXUS
python -X utf8 tests\phase11\live_proof_device.py
