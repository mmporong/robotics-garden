[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot "garden_publish.py"
$pythonConsole = (Get-Command python.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$pythonWindow = Join-Path (Split-Path -Parent $pythonConsole) "pythonw.exe"
$python = if (Test-Path -LiteralPath $pythonWindow -PathType Leaf) { $pythonWindow } else { $pythonConsole }

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 6) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 30) `
    -RunOnlyIfNetworkAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

$dailyAction = New-ScheduledTaskAction -Execute $python -Argument ('"{0}" --mode daily' -f $runner) -WorkingDirectory $repo
$dailyTrigger = New-ScheduledTaskTrigger -Daily -At "08:00"
Register-ScheduledTask -TaskName "RoboticsGarden-Daily-Simulation" -Action $dailyAction -Trigger $dailyTrigger -Settings $settings -Principal $principal -Description "매일 08:00 시뮬레이션 리서치 한 편을 가든에 발행" -Force | Out-Null

$weeklyAction = New-ScheduledTaskAction -Execute $python -Argument ('"{0}" --mode weekly' -f $runner) -WorkingDirectory $repo
$weeklyTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "07:00"
Register-ScheduledTask -TaskName "RoboticsGarden-Weekly-Insight" -Action $weeklyAction -Trigger $weeklyTrigger -Settings $settings -Principal $principal -Description "매주 월요일 07:00 시뮬레이션 리서치 주간 종합 인사이트를 가든에 발행" -Force | Out-Null

Get-ScheduledTask -TaskName "RoboticsGarden-Daily-Simulation", "RoboticsGarden-Weekly-Insight" |
    Select-Object TaskName, State
