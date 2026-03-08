$ErrorActionPreference = "Stop"

$scriptPath = $MyInvocation.MyCommand.Path
if (-not $scriptPath) {
    throw "Nao foi possivel resolver o caminho do script stop.ps1."
}

$projectRoot = Split-Path -Parent $scriptPath
$projectRootRegex = [regex]::Escape($projectRoot)

$candidates = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "python.exe" -and $_.CommandLine -like "*langgraph_terminal.main*"
}

$targets = @()
foreach ($proc in $candidates) {
    if ($proc.CommandLine -match $projectRootRegex -or $proc.CommandLine -match [regex]::Escape(".venv312\Scripts\python.exe")) {
        $targets += $proc
    }
}

if (-not $targets -or $targets.Count -eq 0) {
    Write-Host "[STOP] Nenhuma instancia da TUI encontrada para este projeto."
    exit 0
}

$ids = $targets | Select-Object -ExpandProperty ProcessId
Stop-Process -Id $ids -Force
Write-Host ("[STOP] Instancias finalizadas: " + ($ids -join ", "))
