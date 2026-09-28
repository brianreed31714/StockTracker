@echo off
setlocal
cd /d "%~dp0"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set REVIEWDATE=%%i

echo ============================================================
echo StockTracker Agentic Daily Review
echo Review date: %REVIEWDATE%
echo ============================================================
echo.

echo [0/4] Updating local repo...
git pull --ff-only
if errorlevel 1 goto :fail

echo.
echo [1/4] Building sanitized daily performance bundle...
python build_daily_review_bundle.py --date %REVIEWDATE%
if errorlevel 1 goto :fail

echo.
echo [2/4] Running GPT model review...
python daily_model_review.py --date %REVIEWDATE%
if errorlevel 1 goto :fail

echo.
echo [3/4] Publishing proposal registry + REVIEW.md...
python proposal_registry.py publish --date %REVIEWDATE%
if errorlevel 1 goto :fail

echo.
echo [4/4] Syncing proposals + latest performance to GitHub...
python sync_proposals_to_git.py --message "Publish StockTracker review %REVIEWDATE%"
if errorlevel 1 goto :fail

echo.
echo ============================================================
echo StockTracker daily review complete.
echo ============================================================
echo.
echo Ask ChatGPT:
echo   How is StockTracker performing?
echo   Review today's StockTracker proposals
echo.
echo To approve:
echo   Approve P-STOCK-YYYYMMDD-NN
echo.
exit /b 0

:fail
echo.
echo ============================================================
echo StockTracker agentic daily review FAILED.
echo ============================================================
exit /b 1
