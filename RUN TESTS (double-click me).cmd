@echo off
title Shelter Inventory Manager - tests
cd /d "%~dp0"
py tests.py
echo.
echo (No window opens - the tests only check the data layer. "OK" at the end means all passed.)
pause
