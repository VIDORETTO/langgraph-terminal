$ErrorActionPreference = "Stop"

$scriptPath = $MyInvocation.MyCommand.Path
if (-not $scriptPath) {
    throw "Nao foi possivel resolver o caminho do script finalizar.ps1."
}

$projectRoot = Split-Path -Parent $scriptPath
$stopScript = Join-Path $projectRoot "stop.ps1"

if (-not (Test-Path $stopScript)) {
    throw "Arquivo stop.ps1 nao encontrado em $projectRoot."
}

& $stopScript
