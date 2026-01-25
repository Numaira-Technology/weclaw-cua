@echo off
:: WeChat Removal Workflow Launcher (Desktop Mode)
:: Double-click this file to start the Control Panel

cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0start.ps1"
