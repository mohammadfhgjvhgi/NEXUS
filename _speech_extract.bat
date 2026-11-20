@echo off
cd /d M:\NEXUS
echo === EXTRACT START === > _speech_extract.log
dir models\whisper-tiny.tar.bz2 | findstr tar >> _speech_extract.log
python -c "import tarfile; tarfile.open(r'M:\NEXUS\models\whisper-tiny.tar.bz2', 'r:bz2').extractall(r'M:\NEXUS\models'); print('TARFILE_OK')" >> _speech_extract.log 2>&1
echo EXTRACT_EXIT=%ERRORLEVEL% >> _speech_extract.log
dir /b models >> _speech_extract.log
dir /b models\sherpa-onnx-whisper-tiny >> _speech_extract.log 2>&1
echo === EXTRACT DONE === >> _speech_extract.log
