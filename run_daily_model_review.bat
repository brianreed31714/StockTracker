@echo off
setlocal
cd /d "%~dp0"

if not "%~1"=="" (
  set REVIEWDATE=%~1
) else (
  for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set REVIEWDATE=%%i
)

echo ============================================================
echo StockTracker Post-Close Daily Review
echo Review date: %REVIEWDATE%
echo ============================================================
echo.

echo [0/6] Updating local repo...
git pull --ff-only
if errorlevel 1 goto :fail_before_lock

python post_close_review_guard.py begin --date %REVIEWDATE%
if errorlevel 20 goto :already_done
if errorlevel 1 goto :fail_before_lock

echo.
echo [1/6] Building sanitized daily performance bundle...
python build_daily_review_bundle.py --date %REVIEWDATE%
if errorlevel 1 goto :fail

echo.
echo [2/6] Publishing sanitized row-level supporting evidence...
python publish_supporting_evidence.py --date %REVIEWDATE%
if errorlevel 1 goto :fail

echo.
echo [3/6] Running GPT model review over full-log summaries and integrity checks...
python daily_model_review.py --date %REVIEWDATE%
if errorlevel 1 goto :fail

echo.
echo [4/6] Publishing proposal registry + REVIEW.md...
python proposal_registry.py publish --date %REVIEWDATE%
if errorlevel 1 goto :fail

echo.
echo [5/6] Syncing evidence, proposals, and latest performance to GitHub...
python sync_proposals_to_git.py --message "Publish StockTracker review and evidence %REVIEWDATE%"
if errorlevel 1 goto :fail

echo.
echo [6/6] Marking post-close review complete...
python post_close_review_guard.py complete --date %REVIEWDATE%
if errorlevel 1 goto :fail_before_lock

echo.
echo ============================================================
echo StockTracker post-close review complete.
echo ============================================================
exit /b 0

:already_done
echo StockTracker post-close review already completed or is running.
exit /b 0

:fail
python post_close_review_guard.py fail --date %REVIEWDATE% --error "daily review pipeline failed"
echo.
echo ============================================================
echo StockTracker post-close daily review FAILED.
echo ============================================================
exit /b 1

:fail_before_lock
echo.
echo ============================================================
echo StockTracker post-close daily review could not start.
echo ============================================================
exit /b 1
