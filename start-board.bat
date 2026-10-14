@echo off
cd /d "%~dp0"

if exist venv\Scripts\activate.bat (
  call venv\Scripts\activate.bat
) else (
  call .venv\Scripts\activate.bat
)

rem Open the browser after the server has had a moment to start
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:5000/"

echo Productivity Board is running. Close this window to stop it.
python backend\app.py
pause