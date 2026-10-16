<#
    TRACE task runner (PowerShell stand-in for make).

    Usage:  .\tasks.ps1 <task> [extra args]
    Tasks:  test lint fmt demo dashboard bench fetch-models fairness train
            up down logs smoke clean help

    If Windows reports "running scripts is disabled on this system", allow
    local scripts once for your account:
        Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
    or run a single task without changing policy:
        powershell -ExecutionPolicy Bypass -File .\tasks.ps1 test

    Keep this file ASCII-only: Windows PowerShell 5.1 reads BOM-less files as ANSI.
#>

# Plain param block on purpose: [Parameter()] attributes would make this an
# advanced script with common parameters (-OutVariable, -OutBuffer, ...), and a
# forwarded argument such as --out would then fail as ambiguous.
param([string]$Task = "help")
$Rest = $args

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"   # rupee sign and superscripts print on Windows consoles

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Use-Venv {
    $activate = Join-Path $root ".venv\Scripts\Activate.ps1"
    if (Test-Path $activate) { . $activate }
    else { Write-Host "No .venv found - using the current Python." -ForegroundColor Yellow }
}

function Assert-Exists([string]$path, [string]$milestone) {
    if (-not (Test-Path $path)) {
        Write-Host "$path does not exist yet - it lands in $milestone (see PLAN.md)." -ForegroundColor Yellow
        exit 1
    }
}

function Invoke-Step([string]$label, [scriptblock]$block) {
    Write-Host "`n=== $label ===" -ForegroundColor Cyan
    & $block
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $label (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

switch ($Task.ToLower()) {

    "test" {
        Use-Venv
        Invoke-Step "pytest" { python -m pytest -q @Rest }
    }

    "lint" {
        Use-Venv
        Invoke-Step "ruff"  { python -m ruff check . }
        Invoke-Step "mypy"  { python -m mypy --strict examfp service ml }
    }

    "fmt" {
        Use-Venv
        Invoke-Step "ruff format" { python -m ruff format . }
        Invoke-Step "ruff fix"    { python -m ruff check . --fix }
    }

    "demo" {
        Use-Venv
        Invoke-Step "demo" { python -m examfp.cli demo @Rest }
    }

    "dashboard" {
        Use-Venv
        Invoke-Step "dashboard" { python -m api.dashboard @Rest }
        Write-Host "`nOpen out\dashboard.html in a browser" -ForegroundColor Green
    }

    "bench" {
        Use-Venv
        Invoke-Step "benchmark" { python -m eval.bench @Rest }
        Write-Host "`nResults: eval\out\results.csv, eval\out\results_by_region.csv" -ForegroundColor Green
    }

    "fetch-models" {
        Use-Venv
        Invoke-Step "fetch the pinned NLI model into models\" { python -m ml.fetch_models @Rest }
    }

    "fairness" {
        # M6 acceptance with the real NLI model. A missing model or extra FAILS
        # here (a plain test run only skips), so this cannot pass vacuously.
        Use-Venv
        $env:TRACE_REQUIRE_LOCAL_MODEL = "1"
        Invoke-Step "fairness acceptance (local model)" { python -m pytest -q -rxX -m local_model tests\fairness @Rest }
        Invoke-Step "NLI reliability (held-out set, fixture agreement)" { python -m eval.nli_reliability }
    }

    "train" {
        Assert-Exists "ml\train_decoder.py" "M9"
        Use-Venv
        Invoke-Step "train decoder" { python -m ml.train_decoder @Rest }
    }

    "up" {
        Assert-Exists "deploy\docker-compose.yml" "M14"
        Invoke-Step "docker compose up" { docker compose -f deploy\docker-compose.yml up -d --build }
        Write-Host "`nAPI  http://localhost:8000/docs" -ForegroundColor Green
        Write-Host "Web  http://localhost:5173"       -ForegroundColor Green
    }

    "down" {
        Assert-Exists "deploy\docker-compose.yml" "M14"
        Invoke-Step "docker compose down" { docker compose -f deploy\docker-compose.yml down }
    }

    "logs" {
        Assert-Exists "deploy\docker-compose.yml" "M14"
        docker compose -f deploy\docker-compose.yml logs -f @Rest
    }

    "smoke" {
        Assert-Exists "service\smoke.py" "M14"
        Use-Venv
        $target = if ($Rest -and $Rest[0]) { $Rest[0] } else { "http://localhost:8000" }
        Invoke-Step "smoke test against $target" { python -m service.smoke --base-url $target }
    }

    "clean" {
        Write-Host "Removing build and run artefacts..." -ForegroundColor Yellow
        foreach ($p in @("out", "eval\out", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "build")) {
            if (Test-Path $p) { Remove-Item -Recurse -Force $p }
        }
        Get-ChildItem -Recurse -Directory -Filter "__pycache__" |
            ForEach-Object { Remove-Item -Recurse -Force $_.FullName }
        Write-Host "Clean." -ForegroundColor Green
    }

    default {
        Write-Host @"
TRACE task runner

  .\tasks.ps1 test       run pytest
  .\tasks.ps1 lint       ruff check + mypy --strict
  .\tasks.ps1 fmt        ruff format + autofix
  .\tasks.ps1 demo       end-to-end CLI demo
  .\tasks.ps1 dashboard  static HTML dashboard -> out\dashboard.html
  .\tasks.ps1 bench      evaluation sweeps -> eval\out\
  .\tasks.ps1 fetch-models  download the pinned NLI model -> models\
  .\tasks.ps1 fairness   M6 acceptance + NLI reliability (needs the model)
  .\tasks.ps1 train      fine-tune the neural decoder
  .\tasks.ps1 up         docker compose up (api, worker, db, web)
  .\tasks.ps1 down       docker compose down
  .\tasks.ps1 logs       follow compose logs
  .\tasks.ps1 smoke      smoke test a running stack
  .\tasks.ps1 clean      remove caches and generated output
"@
    }
}
