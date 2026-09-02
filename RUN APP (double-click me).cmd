@echo off
title Shelter Inventory Manager
cd /d "%~dp0"
where pyw >nul 2>nul
if errorlevel 1 (
    echo Python's "py" launcher was not found. Install Python from python.org
    echo and tick "Add python.exe to PATH", then run this again.
    pause
    exit /b 1
)
py -c "import webview" 2>nul || py -m pip install --quiet pywebview
start "" pyw shelter_inventory.py
