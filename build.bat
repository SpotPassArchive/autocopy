@ECHO off
pip install -r requirements.txt
python -m PyInstaller --onefile autocopy.py
