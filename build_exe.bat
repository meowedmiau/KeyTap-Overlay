@echo off
setlocal
cd /d "%~dp0"

if not exist requirements-build.txt (
    echo Missing requirements-build.txt
    exit /b 1
)

for /f "usebackq delims=" %%V in ("VERSION") do set VERSION=%%V
if not defined VERSION (
    echo VERSION file is empty.
    exit /b 1
)

if not exist ".build-tools\PyInstaller\__main__.py" (
    py -m pip install --target .build-tools -r requirements-build.txt
    if errorlevel 1 exit /b %errorlevel%
)

set "PYTHONPATH=%CD%\.build-tools"
py -m PyInstaller --noconfirm --clean --windowed --onefile --name KeyTap-Overlay --icon "assets\keytap.ico" --add-data "data;data" --add-data "VERSION;." --collect-all imageio_ffmpeg main.pyw
if errorlevel 1 exit /b %errorlevel%

powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'dist\KeyTap-Overlay.exe','README.md','LICENSE' -DestinationPath 'dist\KeyTap-Overlay-%VERSION%-Windows.zip' -Force"
if errorlevel 1 exit /b %errorlevel%

echo.
echo Build complete:
echo   dist\KeyTap-Overlay.exe
echo   dist\KeyTap-Overlay-%VERSION%-Windows.zip
endlocal