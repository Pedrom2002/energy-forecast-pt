.PHONY: help install test lint format docker-build docker-run docker-stop deploy-aws deploy-azure deploy-gcp clean

help:
	@echo "Energy Forecast PT - Makefile Commands"
	@echo ""
	@echo "Development:"
	@echo "  make install        - Install dependencies"
	@echo "  make test           - Run tests"
	@echo "  make lint           - Run linters"
	@echo "  make format         - Format code"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build   - Build Docker image"
	@echo "  make docker-run     - Run Docker container"
	@echo "  make docker-stop    - Stop Docker container"
	@echo "  make docker-logs    - Show container logs"
	@echo ""
	@echo "Deploy:"
	@echo "  make deploy-aws     - Deploy to AWS ECS"
	@echo "  make deploy-azure   - Deploy to Azure"
	@echo "  make deploy-gcp     - Deploy to GCP"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean          - Remove build artifacts"

# Development
install:
	pip install -r requirements.txt
	pip install pytest pytest-cov black flake8 isort

test:
	pytest tests/ --cov=src --cov-report=html --cov-report=term

lint:
	@echo "Running black..."
	black --check src/
	@echo "Running isort..."
	isort --check-only src/
	@echo "Running flake8..."
	flake8 src/ --max-line-length=120 --ignore=E203,W503

format:
	@echo "Formatting with black..."
	black src/
	@echo "Sorting imports with isort..."
	isort src/
	@echo "Done!"

# Docker
docker-build:
	docker build -t energy-forecast-api:latest .

docker-run:
	docker run -d -p 8000:8000 --name energy-forecast-api energy-forecast-api:latest
	@echo "API running at http://localhost:8000"
	@echo "Docs at http://localhost:8000/docs"

docker-stop:
	docker stop energy-forecast-api || true
	docker rm energy-forecast-api || true

docker-logs:
	docker logs -f energy-forecast-api

docker-compose-up:
	docker-compose up -d
	@echo "Services started!"

docker-compose-down:
	docker-compose down

# Deploy
deploy-aws:
	@chmod +x deploy/deploy-aws.sh
	./deploy/deploy-aws.sh

deploy-azure:
	@chmod +x deploy/deploy-azure.sh
	./deploy/deploy-azure.sh

deploy-gcp:
	@chmod +x deploy/deploy-gcp.sh
	./deploy/deploy-gcp.sh

# Cleanup
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ htmlcov/ .coverage
	@echo "Cleanup complete!"

# API
run-api:
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# Notebooks
jupyter:
	jupyter notebook notebooks/
