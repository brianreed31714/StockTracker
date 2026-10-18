# Read-only two-project baseline audit.
# Never runs git fetch/pull, creates tasks, stops processes, trades, or uploads files.
$ErrorActionPreference = 'Stop'
$InfrastructureDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ThisRepo = Split-Path -Parent $InfrastructureDir
$Parent = Split-Path -Parent $ThisRepo

Write-Host ''
Write-Host '=== STOCK + CRYPTO INFRASTRUCTURE BASELINE ==='
Write-Host 'Read-only inspection; local ignored evidence; no Git pushes or restarts.'
$Issues = @()

foreach ($Project in @('CryptoTracker', 'StockTracker')) {
    $Repo = Join-Path $Parent $Project
    $Contract = Join-Path $Repo 'infrastructure\registry_contract.py'
    $Probe = Join-Path $Repo 'infrastructure\runtime_inventory.py'
    $Report = Join-Path $Repo 'deploy\state\infrastructure_inventory.json'
    Write-Host ''
    Write-Host ("--- {0} ---" -f $Project)

    if (-not (Test-Path $Contract) -or -not (Test-Path $Probe)) {
        Write-Host 'NOT READY: latest infrastructure files missing locally. No sync attempted.'
        $Issues += "$Project files missing"
        continue
    }
    Push-Location $Repo
    try {
        $CheckOutput = & python -m infrastructure.registry_contract --local-safety 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'BLOCKED: registry safety validation failed. No runtime probe performed.'
            $Issues += "$Project registry safety failed"
            $CheckOutput | Select-Object -Last 4 | ForEach-Object { Write-Host $_ }
            continue
        }
        Write-Host 'Registry safety: PASS'

        $ProbeOutput = & python -m infrastructure.runtime_inventory --write-local 2>&1
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Report)) {
            Write-Host 'HOST INVENTORY UNAVAILABLE; no changes made.'
            $Issues += "$Project host probe failed"
            $ProbeOutput | Select-Object -Last 4 | ForEach-Object { Write-Host $_ }
            continue
        }
        $State = Get-Content $Report -Raw | ConvertFrom-Json
        Write-Host ("Host snapshot consistent: {0} (release verified: {1})" -f $State.host_snapshot_consistent, $State.release_verified)
        Write-Host ("Startup launch provenance verified: {0} (requires separate logon/reboot evidence)" -f $State.startup_provenance_verified)
        Write-Host ("Local Git HEAD: {0}" -f $State.git_head)
        Write-Host ("Local active release commit: {0}" -f $State.active_manifest_commit)
        foreach ($Entry in $State.components.PSObject.Properties) {
            $Cid = $Entry.Name
            $Proc = $Entry.Value.process
            $Artifact = $Entry.Value.artifact
            $Script = $Entry.Value.script_version
            $ScriptStatus = if ($Script) { $Script.state } else { 'UNKNOWN' }
            Write-Host ("  {0}: PID evidence={1} [{2}]; script={3}; artifact={4}" -f
                $Cid, $Proc.state, ($Proc.pids -join ','), $ScriptStatus, $Artifact.state)
            if ($ScriptStatus -eq 'MISMATCH') {
                Write-Host ("    Expected: {0} | Observed: {1}" -f $Script.expected_script, $Script.observed_script)
            }
        }
        foreach ($Task in $State.tasks) {
            Write-Host ("  Task {0}: {1}, RunLevel={2}, LastResult={3}, LastRunUTC={4}" -f $Task.name, $Task.state, $Task.run_level, $Task.last_result, $Task.last_run_utc)
        }
        if ($State.warnings.Count -gt 0) {
            Write-Host ("Warnings ({0}):" -f $State.warnings.Count)
            foreach ($Warning in $State.warnings) { Write-Host ("  - {0}" -f $Warning) }
            $Issues += "$Project has host warnings"
        }
        if ($State.cautions.Count -gt 0) {
            Write-Host ("Startup/recovery cautions ({0}; not service failures):" -f $State.cautions.Count)
            foreach ($Caution in $State.cautions) { Write-Host ("  - {0}" -f $Caution) }
        }
        Write-Host 'Local evidence: deploy\state\infrastructure_inventory.json (gitignored)'
    } finally {
        Pop-Location
    }
}
Write-Host ''
if ($Issues.Count) {
    Write-Host ("=== AUDIT INCOMPLETE / NEEDS ATTENTION ({0} issue group(s)) ===" -f $Issues.Count)
} else {
    Write-Host '=== READ-ONLY AUDIT FINISHED; RELEASE ATTESTATION STILL REQUIRED ==='
}
Write-Host 'This check did not stop, restart, or deploy any service.'
