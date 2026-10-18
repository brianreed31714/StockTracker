# StockTracker scheduled-task failure diagnosis; READ ONLY.
# No Git operations, service restarts, scheduled-task changes, reviews, or trades.
$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Write-Host '=== STOCKTRACKER SCHEDULER / DAILY REVIEW DIAGNOSTIC ==='
Write-Host 'Read-only: task metadata, error codes, parent process, and review state.'
$taskNames = @('StockTracker Supervisor', 'StockTracker Daily Review')
foreach ($name in $taskNames) {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    Write-Host ''
    Write-Host ("TASK: {0}" -f $name)
    if ($null -eq $task) {
        Write-Host 'Task not found'
        continue
    }
    $info = Get-ScheduledTaskInfo -TaskName $name -ErrorAction SilentlyContinue
    $lastResult = if ($info) { [long]$info.LastTaskResult } else { 0 }
    $hex = "0x{0:X8}" -f ($lastResult -band 0xFFFFFFFFL)
    Write-Host ("State={0}; LastResult={1} ({2}); LastRun={3}" -f $task.State, $lastResult, $hex, $info.LastRunTime.ToString('o'))
    Write-Host ("TaskLogonType={0}; RunLevel={1}; MultipleInstances={2}" -f $task.Principal.LogonType, $task.Principal.RunLevel, $task.Settings.MultipleInstances)
    foreach ($trig in @($task.Triggers)) {
        $triggerType = ([string]$trig.CimClass.CimClassName) -replace '^MSFT_Task', ''
        Write-Host ("Trigger={0}; Enabled={1}" -f $triggerType, $trig.Enabled)
    }
    foreach ($action in @($task.Actions)) {
        $exe = [System.IO.Path]::GetFileName([string]$action.Execute)
        $argsText = [string]$action.Arguments
        $scriptName = if ($argsText -match '([\w.-]+\.(?:py|bat))') { $Matches[1] } else { '(not identifiable)' }
        Write-Host ("ActionExe={0}; ActionScript={1}; WorkingDirConfigured={2}" -f $exe, $scriptName, (![string]::IsNullOrWhiteSpace([string]$action.WorkingDirectory)))
    }
}
Write-Host ''
Write-Host 'SUPERVISOR PROCESS START AND PARENT (metadata only):'
$inventory = Join-Path $Repo 'deploy\state\infrastructure_inventory.json'
if (Test-Path $inventory) {
    $data = Get-Content $inventory -Raw | ConvertFrom-Json
    $pids = @($data.components.supervisor.process.pids)
    foreach ($supervisorPid in $pids) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $supervisorPid" -ErrorAction SilentlyContinue
        if ($null -eq $proc) {
            Write-Host ("Supervisor PID {0} exited since inventory." -f $supervisorPid)
            continue
        }
        $parentProc = Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.ParentProcessId)" -ErrorAction SilentlyContinue
        $parentName = if ($null -eq $parentProc) { '(parent exited or inaccessible)' } else { $parentProc.Name }
        Write-Host ("Supervisor PID={0}; StartedUTC={1}; ParentPID={2}; ParentExe={3}" -f $proc.ProcessId, $proc.CreationDate.ToUniversalTime().ToString('o'), $proc.ParentProcessId, $parentName)
    }
} else { Write-Host 'No existing local infrastructure inventory.' }
Write-Host ''
Write-Host 'LATEST POST-CLOSE REVIEW STATE (no raw error text):'
$stateFile = Join-Path $Repo 'post_close_review_state.json'
if (Test-Path $stateFile) {
    try {
        $state = Get-Content $stateFile -Raw | ConvertFrom-Json
        Write-Host ("Date={0}; Status={1}; Attempts={2}; Started={3}; Finished={4}; ErrorPresent={5}" -f $state.review_date, $state.status, $state.attempts, $state.started_at, $state.finished_at, ([bool]$state.error))
    } catch { Write-Host 'Review state file exists but is unreadable.' }
} else { Write-Host 'Review state file not present at compatibility mirror.' }
$perf = Join-Path $Repo 'analysis\performance\latest.json'
if (Test-Path $perf) {
    $item = Get-Item $perf
    Write-Host ("Tracked performance summary last local write: {0}" -f $item.LastWriteTime.ToString('o'))
}
Write-Host ''
Write-Host 'RECENT TASK SCHEDULER EVENTS (event IDs and return codes only):'
try {
    $events = @(Get-WinEvent -FilterHashtable @{ LogName='Microsoft-Windows-TaskScheduler/Operational'; StartTime=(Get-Date).AddDays(-30) } -MaxEvents 1500 -ErrorAction Stop)
    foreach ($name in $taskNames) {
        $matching = @($events | Where-Object { ([string]$_.Message).Contains($name) } | Sort-Object TimeCreated -Descending | Select-Object -First 8)
        Write-Host ("{0}: {1} matching recent event(s)" -f $name, $matching.Count)
        foreach ($evt in $matching) {
            $message = [string]$evt.Message
            $resultCode = if ($message -match '(?:return|error|result) code[:\s]+(0x[0-9A-Fa-f]+|\d+)') { $Matches[1] } else { '(not present)' }
            Write-Host ("  {0} EventID={1} Level={2} ResultCode={3}" -f $evt.TimeCreated.ToUniversalTime().ToString('o'), $evt.Id, $evt.LevelDisplayName, $resultCode)
        }
    }
} catch { Write-Host 'Task Scheduler Operational event history unavailable or disabled.' }
Write-Host ''
Write-Host 'Diagnostic complete. No tasks or services were modified.'
