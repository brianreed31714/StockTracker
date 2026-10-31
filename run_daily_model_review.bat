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

echo [0/6] Deployment agent owns Git synchronization; review reads local scripts only.

python post_close_review_guard.py begin --date %REVIEWDATE%
if errorlevel 23 goto :auth_blocked
if errorlevel 22 goto :retry_cooldown
if errorlevel 21 goto :retry_exhausted
if errorlevel 20 goto :already_done
if errorlevel 1 goto :fail_before_lock

echo.
echo [1/6] Building sanitized daily performance bundle...
set FAILSTAGE=bundle
python build_daily_review_bundle.py --date %REVIEWDATE%
if errorlevel 1 goto :fail

echo.
echo [2/6] Publishing sanitized row-level supporting evidence...
set FAILSTAGE=evidence
python publish_supporting_evidence.py --date %REVIEWDATE%
if errorlevel 1 goto :fail

echo.
echo [3/6] Running GPT model review over full-log summaries and integrity checks...
set FAILSTAGE=model_review
python daily_model_review.py --date %REVIEWDATE% --defer-notification
if errorlevel 3 goto :fail
if errorlevel 2 goto :auth_failure
if errorlevel 1 goto :fail

echo.
echo [4/6] Publishing proposal registry + REVIEW.md...
set FAILSTAGE=proposal_publish
python proposal_registry.py publish --date %REVIEWDATE%
if errorlevel 1 goto :fail

echo.
echo [5/6] Syncing evidence, proposals, and latest performance to GitHub...
set FAILSTAGE=github_sync
python sync_proposals_to_git.py --message "Publish StockTracker review and evidence %REVIEWDATE%"
if errorlevel 1 goto :fail

echo.
echo [6/6] Marking post-close review complete...
set FAILSTAGE=guard_complete
python post_close_review_guard.py complete --date %REVIEWDATE%
if errorlevel 1 goto :fail_before_lock

echo.
echo ============================================================
echo StockTracker post-close review complete.
echo ============================================================
rem Review/publication is complete; notification is a separate, dated phase.
python daily_model_review.py --date %REVIEWDATE% --record-publication
if errorlevel 1 goto :notification_failed
python daily_model_review.py --date %REVIEWDATE% --notify-only
if errorlevel 1 goto :notification_failed
rem Optional, read-only Windows activation receipt. Never changes review result.
python -m infrastructure.windows_activation_attestation --notify
if errorlevel 1 echo StockTracker activation attestation unavailable; review still completed.
exit /b 0

:auth_blocked
echo StockTracker post-close review stopped: previous OpenAI authorization failure.
exit /b 23

:retry_exhausted
echo StockTracker post-close review retry limit reached; needs investigation.
exit /b 21

:retry_cooldown
echo StockTracker post-close review cooldown active. No new attempt started.
exit /b 22

:already_done
echo StockTracker post-close review already completed or is running.
exit /b 0

:auth_failure
python post_close_review_guard.py fail --date %REVIEWDATE% --stage model_review --category AUTHENTICATION --error "OpenAI authorization or API key validation failed"
echo StockTracker review stopped on non-retryable OpenAI authorization failure.
exit /b 2

:fail
python post_close_review_guard.py fail --date %REVIEWDATE% --stage %FAILSTAGE% --error "daily review pipeline failed"
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

:notification_failed
echo Review artifacts completed; publication verification or notification needs attention.
echo Do not rerun the model to resend. Inspect the dated local receipt first.
exit /b 4
