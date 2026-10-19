# In-place update ONLY of StockTracker Daily Review trigger.
# No task re-registration, process restart, Git sync, or trading changes.
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$Name = 'StockTracker Daily Review'
if ([TimeZoneInfo]::Local.Id -ne 'Pacific Standard Time') {
    throw 'Expected Pacific Windows time zone; no change made.'
}
$Task = Get-ScheduledTask -TaskName $Name -ErrorAction Stop
if ($Task.State -eq 'Running') { throw 'Review is running; try later.' }
if (@($Task.Actions).Count -ne 1 -or
    -not ([string]$Task.Actions[0].Arguments).Contains('run_daily_model_review.bat')) {
    throw 'Unexpected scheduled task action; no change made.'
}
if (@($Task.Triggers).Count -ne 1 -or
    ([string]$Task.Triggers[0].CimClass.CimClassName) -notlike '*WeeklyTrigger*') {
    throw 'Unexpected trigger; no change made.'
}
Write-Host "Current trigger: $($Task.Triggers[0].StartBoundary)"
if (-not $Apply) {
    Write-Host 'PREVIEW ONLY. Re-run with -Apply to use 13:35 Pacific weekdays.'
    exit 0
}
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 1:35PM
Set-ScheduledTask -TaskName $Name -Trigger $Trigger -ErrorAction Stop | Out-Null
$Updated = Get-ScheduledTask -TaskName $Name -ErrorAction Stop
if (@($Updated.Triggers).Count -ne 1 -or
    ([datetime]$Updated.Triggers[0].StartBoundary).ToString('HH:mm') -ne '13:35') {
    throw 'Schedule update returned without verified 13:35 trigger.'
}
Write-Host "VERIFIED: Review task now starts weekdays at 13:35 Pacific."
Write-Host 'No StockTracker or CryptoTracker process was restarted.'
