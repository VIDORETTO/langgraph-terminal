$ErrorActionPreference = "Stop"

$scriptPath = $MyInvocation.MyCommand.Path
if (-not $scriptPath) {
    throw "Nao foi possivel resolver o caminho do script iniciar.ps1."
}

$projectRoot = Split-Path -Parent $scriptPath
$runScript = Join-Path $projectRoot "run.ps1"

if (-not (Test-Path $runScript)) {
    throw "Arquivo run.ps1 nao encontrado em $projectRoot."
}

& $runScript
