@echo off
cd /d M:\NEXUS
echo === SETUP START === > _speech_setup.log
python -m pip install --quiet sherpa-onnx numpy >> _speech_setup.log 2>&1
echo PIP_DONE >> _speech_setup.log
if not exist models mkdir models
curl -sL -o models\whisper-tiny.tar.bz2 https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-tiny.tar.bz2
echo DL_EXIT=%ERRORLEVEL% >> _speech_setup.log
tar -xjf models\whisper-tiny.tar.bz2 -C models
echo EXTRACT_EXIT=%ERRORLEVEL% >> _speech_setup.log
dir /b models >> _speech_setup.log
echo === SETUP DONE === >> _speech_setup.log
