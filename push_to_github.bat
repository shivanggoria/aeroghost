@echo off
setlocal
echo =======================================================
echo AeroGhost - Push to GitHub Repository
echo =======================================================
echo.
set /p REPO_URL="Enter your GitHub Repository URL (e.g., https://github.com/USERNAME/aeroghost.git): "

if "%REPO_URL%"=="" (
    echo Error: No repository URL entered. Exiting.
    pause
    exit /b 1
)

echo.
echo Configuring remote 'origin' -> %REPO_URL%
git remote remove origin 2>nul
git remote add origin %REPO_URL%
git branch -M main

echo.
echo Pushing code and release tag to GitHub...
git push -u origin main --tags

echo.
if %errorlevel% equ 0 (
    echo [SUCCESS] AeroGhost has been pushed to GitHub!
    echo The GitHub Actions CI will now automatically build and attach AeroGhost.exe to GitHub Releases.
) else (
    echo [ERROR] Push failed. Please check your GitHub credentials or repository permissions.
)
echo.
pause
