@echo off
title Shelter Inventory Manager - build the .exe
cd /d "%~dp0"

echo.
echo  This turns shelter_inventory.py into ONE file, dist\ShelterInventory.exe,
echo  that a charity can double-click without installing Python.
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo  Python's "py" launcher was not found. Install Python from python.org
    echo  and tick "Add python.exe to PATH", then run this again.
    pause
    exit /b 1
)

echo  [1/3] Running the tests first - if these fail, we do not build.
py tests.py
if errorlevel 1 (
    echo.
    echo  Tests FAILED. Fix them before shipping an .exe to anyone.
    pause
    exit /b 1
)

echo.
echo  [2/3] Installing PyInstaller (only the first time)...
py -m pip install --quiet --upgrade pyinstaller pywebview
if errorlevel 1 (
    echo  Could not install PyInstaller. Are you online?
    pause
    exit /b 1
)

echo.
echo  [3/3] Building...
py -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name ShelterInventory ^
    --icon icon.ico ^
    --add-data "icon.ico;." ^
    --add-data "webui;webui" ^
    --hidden-import shelter_inventory_classic ^
    shelter_inventory.py
if errorlevel 1 (
    echo  Build FAILED - read the messages above.
    pause
    exit /b 1
)

echo.
echo  Done. Your file is:   %~dp0dist\ShelterInventory.exe
echo.
echo  First time you run it Windows may show "Windows protected your PC".
echo  Click "More info" then "Run anyway" - see README.md for why.
echo.
start "" explorer.exe "%~dp0dist"
pause
