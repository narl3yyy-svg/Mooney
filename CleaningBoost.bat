@echo off
cd /d "%~dp0"
python -c "import numpy" 2>nul || python -m pip install -r requirements.txt
python cleaning_boost.py
