@echo off
echo === Building PowerTeamDashboard.exe ===
call venv\Scripts\activate
pyinstaller main.spec --clean
if errorlevel 1 (
    echo ERROR: Build failed.
    pause
    exit /b 1
)
echo.
echo === Build complete ===
echo Distributable folder: dist\PowerTeamDashboard\
echo Copy the entire dist\PowerTeamDashboard\ folder to deploy.
pause
