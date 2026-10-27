@echo off
cd /d "%~dp0"
echo Obnovlenie yt-dlp, certifi i customtkinter v venv...
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe -m pip install --upgrade -r requirements.txt
) else (
    echo venv ne nayden. Sozdayu...
    py -m venv venv
    venv\Scripts\python.exe -m pip install --upgrade -r requirements.txt
)
echo.
echo Gotovo. Zapustite start.bat
pause
