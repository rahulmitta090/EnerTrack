@echo off
echo ====================================================
echo        EnerTrack GitHub Push Utility
echo ====================================================
echo.

where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Git is not installed or not in your PATH.
    echo Please install Git from: https://git-scm.com/download/win
    echo After installing, restart your terminal and re-run this script.
    pause
    exit /b 1
)

set /p REPO_URL="Enter your GitHub Repository URL (e.g., https://github.com/USER/enertrack.git): "
if "%REPO_URL%"=="" (
    echo [ERROR] No URL entered. Aborting.
    pause
    exit /b 1
)

echo.
echo [1/5] Initializing Git...
if not exist ".git" (
    git init
)

echo [2/5] Staging files...
git add .

echo [3/5] Committing changes...
git commit -m "Initial commit: EnerTrack - Energy Consumption Anomaly Detector"

echo [4/5] Setting main branch...
git branch -M main

echo [5/5] Connecting remote and pushing...
git remote remove origin 2>nul
git remote add origin %REPO_URL%
git push -u origin main

echo.
echo ====================================================
echo   Successfully pushed EnerTrack to GitHub!
echo ====================================================
pause
