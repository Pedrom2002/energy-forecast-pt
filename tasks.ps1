# PowerShell task runner for Energy Forecast PT
# Alternative to Makefile for Windows users
# Usage: .\tasks.ps1 <command>

param(
    [Parameter(Position=0)]
    [string]$Command = "help"
)

function Show-Help {
    Write-Host "`n=================================" -ForegroundColor Cyan
    Write-Host "Energy Forecast PT - Tasks" -ForegroundColor Cyan
    Write-Host "=================================" -ForegroundColor Cyan
    Write-Host "`nUsage: .\tasks.ps1 <command>`n" -ForegroundColor Yellow

    Write-Host "Development:" -ForegroundColor Green
    Write-Host "  install        - Install dependencies"
    Write-Host "  test           - Run tests with coverage"
    Write-Host "  test-quick     - Run tests without coverage"
    Write-Host "  lint           - Run code linters"
    Write-Host "  format         - Format code with black and isort"

    Write-Host "`nDocker:" -ForegroundColor Green
    Write-Host "  docker-build   - Build Docker image"
    Write-Host "  docker-run     - Run Docker container"
    Write-Host "  docker-stop    - Stop Docker container"
    Write-Host "  docker-logs    - Show container logs"
    Write-Host "  compose-up     - Start with docker-compose"
    Write-Host "  compose-down   - Stop docker-compose"

    Write-Host "`nAPI:" -ForegroundColor Green
    Write-Host "  run-api        - Start API server (development)"
    Write-Host "  test-api       - Test API endpoints"

    Write-Host "`nJupyter:" -ForegroundColor Green
    Write-Host "  jupyter        - Start Jupyter notebook server"

    Write-Host "`nDeploy:" -ForegroundColor Green
    Write-Host "  deploy-aws     - Deploy to AWS ECS"
    Write-Host "  deploy-azure   - Deploy to Azure"
    Write-Host "  deploy-gcp     - Deploy to GCP"

    Write-Host "`nCleanup:" -ForegroundColor Green
    Write-Host "  clean          - Remove build artifacts and cache"
    Write-Host "`n"
}

function Install-Dependencies {
    Write-Host "`n[Installing dependencies...]" -ForegroundColor Yellow
    pip install -r requirements.txt
    pip install pytest pytest-cov black flake8 isort
    Write-Host "✓ Dependencies installed!" -ForegroundColor Green
}

function Run-Tests {
    Write-Host "`n[Running tests with coverage...]" -ForegroundColor Yellow
    python -m pytest tests/ --cov=src --cov-report=html --cov-report=term
    Write-Host "`n✓ Tests complete! Open htmlcov/index.html to see coverage report" -ForegroundColor Green
}

function Run-QuickTests {
    Write-Host "`n[Running tests (quick mode)...]" -ForegroundColor Yellow
    python -m pytest tests/ -v
}

function Run-Lint {
    Write-Host "`n[Running linters...]" -ForegroundColor Yellow

    Write-Host "`nChecking code style with black..." -ForegroundColor Cyan
    black --check src/

    Write-Host "`nChecking import order with isort..." -ForegroundColor Cyan
    isort --check-only src/

    Write-Host "`nRunning flake8..." -ForegroundColor Cyan
    flake8 src/ --max-line-length=120 --ignore=E203,W503

    Write-Host "`n✓ Linting complete!" -ForegroundColor Green
}

function Format-Code {
    Write-Host "`n[Formatting code...]" -ForegroundColor Yellow

    Write-Host "Formatting with black..." -ForegroundColor Cyan
    black src/

    Write-Host "Sorting imports with isort..." -ForegroundColor Cyan
    isort src/

    Write-Host "`n✓ Code formatted!" -ForegroundColor Green
}

function Build-Docker {
    Write-Host "`n[Building Docker image...]" -ForegroundColor Yellow
    docker build -t energy-forecast-api:latest .
    Write-Host "✓ Docker image built!" -ForegroundColor Green
}

function Run-Docker {
    Write-Host "`n[Starting Docker container...]" -ForegroundColor Yellow
    docker run -d -p 8000:8000 --name energy-forecast-api energy-forecast-api:latest
    Write-Host "`n✓ Container started!" -ForegroundColor Green
    Write-Host "API running at: http://localhost:8000" -ForegroundColor Cyan
    Write-Host "Docs at: http://localhost:8000/docs" -ForegroundColor Cyan
}

function Stop-Docker {
    Write-Host "`n[Stopping Docker container...]" -ForegroundColor Yellow
    docker stop energy-forecast-api 2>$null
    docker rm energy-forecast-api 2>$null
    Write-Host "✓ Container stopped!" -ForegroundColor Green
}

function Show-DockerLogs {
    Write-Host "`n[Showing container logs...]" -ForegroundColor Yellow
    docker logs -f energy-forecast-api
}

function Start-Compose {
    Write-Host "`n[Starting docker-compose...]" -ForegroundColor Yellow
    docker-compose up -d
    Write-Host "`n✓ Services started!" -ForegroundColor Green
    Write-Host "API: http://localhost:8000" -ForegroundColor Cyan
    Write-Host "Docs: http://localhost:8000/docs" -ForegroundColor Cyan
}

function Stop-Compose {
    Write-Host "`n[Stopping docker-compose...]" -ForegroundColor Yellow
    docker-compose down
    Write-Host "✓ Services stopped!" -ForegroundColor Green
}

function Start-API {
    Write-Host "`n[Starting API server...]" -ForegroundColor Yellow
    Write-Host "Press Ctrl+C to stop`n" -ForegroundColor Cyan
    uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
}

function Test-API {
    Write-Host "`n[Testing API endpoints...]" -ForegroundColor Yellow
    .\test_api.ps1
}

function Start-Jupyter {
    Write-Host "`n[Starting Jupyter notebook...]" -ForegroundColor Yellow
    jupyter notebook notebooks/
}

function Deploy-AWS {
    Write-Host "`n[Deploying to AWS...]" -ForegroundColor Yellow
    bash deploy/deploy-aws.sh
}

function Deploy-Azure {
    Write-Host "`n[Deploying to Azure...]" -ForegroundColor Yellow
    bash deploy/deploy-azure.sh
}

function Deploy-GCP {
    Write-Host "`n[Deploying to GCP...]" -ForegroundColor Yellow
    bash deploy/deploy-gcp.sh
}

function Clean-Project {
    Write-Host "`n[Cleaning project...]" -ForegroundColor Yellow

    # Remove Python cache
    Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path . -Recurse -File -Filter "*.pyc" | Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path . -Recurse -File -Filter "*.pyo" | Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path . -Recurse -Directory -Filter "*.egg-info" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path . -Recurse -Directory -Filter ".pytest_cache" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    # Remove build directories
    Remove-Item -Path "build" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "dist" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "htmlcov" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path ".coverage" -Force -ErrorAction SilentlyContinue

    Write-Host "✓ Cleanup complete!" -ForegroundColor Green
}

# Main command dispatcher
switch ($Command.ToLower()) {
    "help" { Show-Help }
    "install" { Install-Dependencies }
    "test" { Run-Tests }
    "test-quick" { Run-QuickTests }
    "lint" { Run-Lint }
    "format" { Format-Code }
    "docker-build" { Build-Docker }
    "docker-run" { Run-Docker }
    "docker-stop" { Stop-Docker }
    "docker-logs" { Show-DockerLogs }
    "compose-up" { Start-Compose }
    "compose-down" { Stop-Compose }
    "run-api" { Start-API }
    "test-api" { Test-API }
    "jupyter" { Start-Jupyter }
    "deploy-aws" { Deploy-AWS }
    "deploy-azure" { Deploy-Azure }
    "deploy-gcp" { Deploy-GCP }
    "clean" { Clean-Project }
    default {
        Write-Host "`nUnknown command: $Command" -ForegroundColor Red
        Show-Help
    }
}
