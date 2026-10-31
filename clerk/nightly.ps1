# Clerk nightly grading run.
#
# Registered with Task Scheduler to start at 02:00, when spark-01 is idle.
# Each deliverable is a separate pipeline, run one after another, because two
# at once would contend for the same single model slot and finish no sooner.
#
# Register it (run once, from an elevated PowerShell):
#
#   schtasks /Create /TN "Clerk nightly grading" /SC DAILY /ST 02:00 ^
#     /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\saundeb1\Documents\Git\Canvas-Tools\clerk\nightly.ps1" ^
#     /RL LIMITED /F
#
# Then allow it to wake the machine, which schtasks cannot set:
#   Task Scheduler > the task > Conditions > "Wake the computer to run this task"
#
# Check what happened:  Get-Content <clerk>\logs\nightly-*.log -Tail 40

# NOT "Stop". In Windows PowerShell 5.1, redirecting a native command's stderr
# with 2>&1 wraps each line in an ErrorRecord, and under ErrorActionPreference
# Stop that becomes a terminating error. On 2026-10-02 this killed the run
# silently the moment Python wrote its first stderr line: the log ends after
# "[extract] 0.0 min" with no error and nothing was graded.
#
# Redirection is done inside cmd below, where it is just a redirect, so neither
# this setting nor PowerShell's stream handling can swallow a run again.
$ErrorActionPreference = "Continue"
$Clerk = Split-Path -Parent $MyInvocation.MyCommand.Path
$Logs  = Join-Path $Clerk "logs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
$Log = Join-Path $Logs ("nightly-" + (Get-Date -Format "yyyy-MM-dd") + ".log")

# What to grade. Add a line per deliverable; comment one out to skip it.
# Course and assignment ids make each run re-fetch first, so late submissions
# are picked up without anyone remembering to.
$Jobs = @(
    @{ Run = "runs/3100-d03"; Course = "81149"; Assignment = "902904" },
    @{ Run = "runs/4750-d02"; Course = "82426"; Assignment = "892265" }
)

function Log($msg) {
    $line = "{0}  {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
    Write-Output $line
    Add-Content -Path $Log -Value $line -Encoding utf8
}

Set-Location $Clerk
Log "=== nightly run starting ==="

# Fail fast if the box is not there. A run that starts against a dead host just
# produces a log full of connection errors, which is worse than not starting:
# the 2026-09-27 ai-01 run wrote 31 percent failed ratings before anyone noticed.
cmd /c "python -m clerk doctor --host spark >> ""$Log"" 2>&1"
if ($LASTEXITCODE -ne 0) {
    Log "doctor failed, spark-01 is not usable. Nothing was graded."
    exit 1
}
Log "doctor passed"

$failed = 0
foreach ($job in $Jobs) {
    Log ("--- " + $job.Run + " ---")
    if ($job.Course -and $job.Assignment) {
        $fetch = "--course {0} --assignment {1}" -f $job.Course, $job.Assignment
    } else {
        $fetch = ""
    }
    $cmdline = "python -u -m clerk pipeline {0} {1} --host spark >> ""{2}"" 2>&1" -f `
        $job.Run, $fetch, $Log
    cmd /c $cmdline
    if ($LASTEXITCODE -ne 0) {
        Log ($job.Run + " did not finish. Rerunning the same command resumes it.")
        $failed++
    } else {
        Log ($job.Run + " complete")
    }
}

Log ("=== nightly run finished, " + $failed + " of " + $Jobs.Count + " incomplete ===")

# Keep a month of logs, no more.
Get-ChildItem $Logs -Filter "nightly-*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -Force

exit $failed
