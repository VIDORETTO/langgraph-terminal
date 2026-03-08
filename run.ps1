$ErrorActionPreference = "Stop"

$scriptPath = $MyInvocation.MyCommand.Path
if (-not $scriptPath) {
    throw "Nao foi possivel resolver o caminho do script run.ps1."
}

$projectRoot = Split-Path -Parent $scriptPath
$pythonPath = Join-Path $projectRoot ".venv312\Scripts\python.exe"
$envPath = Join-Path $projectRoot ".env"
$envExamplePath = Join-Path $projectRoot ".env.example"

function Write-Step([string]$message) {
    Write-Host "[INIT] $message" -ForegroundColor Cyan
}

Set-Location $projectRoot

if (-not (Test-Path $pythonPath)) {
    Write-Step "Ambiente .venv312 nao encontrado. Criando com Python 3.12..."
    & py -3.12 --version *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.12 nao encontrado. Instale-o e tente novamente."
    }
    & py -3.12 -m venv .venv312
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao criar o ambiente virtual .venv312."
    }
}

Write-Step "Validando ambiente Python..."
& $pythonPath -m pip --version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "pip nao esta funcional em .venv312. Recrie o ambiente."
}

Write-Step "Checando dependencias do projeto..."
& $pythonPath -c "import langgraph_terminal" *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Step "Instalando dependencias com pip install -e ."
    & $pythonPath -m pip install -e .
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao instalar dependencias do projeto."
    }
}

if (-not (Test-Path $envPath) -and (Test-Path $envExamplePath)) {
    Copy-Item $envExamplePath $envPath -Force
    Write-Step "Arquivo .env criado a partir de .env.example."
    Write-Step "Defina OPENAI_API_KEY no .env ou use /key dentro da TUI."
}

Write-Step "Iniciando TUI..."
& $pythonPath -m langgraph_terminal.main
