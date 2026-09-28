# StockTracker startup + weekday daily review installer.
# Run this PowerShell script AS ADMINISTRATOR.
$ErrorActionPreference = "Stop"

$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$Supervisor = Join-Path $Repo "stocktracker_supervisor.py"
$ReviewBat = Join-Path $Repo "run_daily_model_review.bat"
if (-not (Test-Path $Supervisor)) { throw "stocktracker_supervisor.py not found in $Repo" }
if (-not (Test-Path $ReviewBat)) { throw "run_daily_model_review.bat not found in $Repo" }

$Python = (Get-Command python.exe -ErrorAction Stop).Source
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$SupervisorTask = "StockTracker Supervisor"
$ReviewTask = "StockTracker Daily Review"

Write-Host ""
Write-Host "StockTracker agentic task setup"
Write-Host "Repository: $Repo"
Write-Host "Python:     $Python"
Write-Host "User:       $CurrentUser"
Write-Host ""

foreach ($Name in @($SupervisorTask, $ReviewTask)) {
    if (Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
    }
}

$Principal = New-ScheduledTaskPrincipal -UserId $CurrentUser -LogonType Interactive -RunLevel Highest
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew

$SupervisorAction = New-ScheduledTaskAction -Execute $Python -Argument ("`"" + $Supervisor + "`"") -WorkingDirectory $Repo
$SupervisorTrigger = New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser
$SupervisorTrigger.Delay = "PT30S"
Register-ScheduledTask -TaskName $SupervisorTask -Action $SupervisorAction -Trigger $SupervisorTrigger -Principal $Principal -Settings $Settings -Force | Out-Null

# Weekdays at 1:30 PM LOCAL Windows time (intended 4:30 PM Eastern on this PC).
$ReviewAction = New-ScheduledTaskAction -Execute "cmd.exe" -Argument ("/c `"" + $ReviewBat + "`"") -WorkingDirectory $Repo
$ReviewTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 1:30PM
Register-ScheduledTask -TaskName $ReviewTask -Action $ReviewAction -Trigger $ReviewTrigger -Principal $Principal -Settings $Settings -Force | Out-Null

Write-Host "Created scheduled task: $SupervisorTask"
Write-Host "  At logon for $CurrentUser, 30 second delay"
Write-Host "Created scheduled task: $ReviewTask"
Write-Host "  Weekdays at 1:30 PM local Windows time"
Write-Host "No Windows account password was stored."
Write-Host ""
Write-Host "Starting the StockTracker supervisor now for a test..."
Start-ScheduledTask -TaskName $SupervisorTask
Start-Sleep -Seconds 3
$Info = Get-ScheduledTaskInfo -TaskName $SupervisorTask
Write-Host "Supervisor LastTaskResult: $($Info.LastTaskResult)"
Write-Host ""
Write-Host "Future flow: PIN login -> supervisor -> trader/feed/dashboard/deployment agent."
