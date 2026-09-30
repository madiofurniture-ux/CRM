@echo off
set "PATH=C:\Users\jagad\AppData\Local\Temp\nd\node-v20.18.1-win-arm64;%PATH%"
cd /d "C:\Users\jagad\OneDrive - MAdio Furniture\MadioFurniture - Documents\CRM\frontend"
node --version
call npm install --no-audit --no-fund --legacy-peer-deps
echo INSTALL_EXIT=%ERRORLEVEL%
