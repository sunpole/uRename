@echo off
chcp 65001 >nul
python -X utf8 -B "%~dp0uRename.py" --preview
pause
