@echo off
rem SLD Migrator - zapusk okna utility
cd /d "%~dp0"
python sld_migrator.py
if errorlevel 1 pause
