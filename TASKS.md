# Task Runner Guide

This document explains how to run common tasks in this project.

## 🪟 Windows (PowerShell) - Recommended

Since `make` is not available by default on Windows, use the **`tasks.ps1`** script:

### Quick Start

```powershell
# Show all available commands
.\tasks.ps1 help

# Or simply
.\tasks.ps1
```

### Common Commands

```powershell
# Development
.\tasks.ps1 install        # Install dependencies
.\tasks.ps1 test          # Run tests with coverage
.\tasks.ps1 test-quick    # Run tests without coverage
.\tasks.ps1 lint          # Check code style
.\tasks.ps1 format        # Auto-format code

# Docker
.\tasks.ps1 docker-build  # Build Docker image
.\tasks.ps1 docker-run    # Run container
.\tasks.ps1 docker-stop   # Stop container
.\tasks.ps1 docker-logs   # View logs
.\tasks.ps1 compose-up    # Start docker-compose
.\tasks.ps1 compose-down  # Stop docker-compose

# API
.\tasks.ps1 run-api       # Start development server
.\tasks.ps1 test-api      # Test all endpoints

# Jupyter
.\tasks.ps1 jupyter       # Start Jupyter notebooks

# Deploy
.\tasks.ps1 deploy-aws    # Deploy to AWS
.\tasks.ps1 deploy-azure  # Deploy to Azure
.\tasks.ps1 deploy-gcp    # Deploy to GCP

# Cleanup
.\tasks.ps1 clean         # Remove cache and build files
```

### Execution Policy

If you get an execution policy error, run once:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## 🐧 Linux / Mac (Makefile)

If you're on Linux or Mac, use the traditional `Makefile`:

```bash
# Show all available commands
make help

# Development
make install     # Install dependencies
make test        # Run tests with coverage
make lint        # Check code style
make format      # Auto-format code

# Docker
make docker-build   # Build Docker image
make docker-run     # Run container
make docker-stop    # Stop container
make docker-logs    # View logs

# API
make run-api     # Start development server

# Jupyter
make jupyter     # Start Jupyter notebooks

# Deploy
make deploy-aws    # Deploy to AWS
make deploy-azure  # Deploy to Azure
make deploy-gcp    # Deploy to GCP

# Cleanup
make clean       # Remove cache and build files
```

---

## 📋 Command Comparison

| Task | Windows (PowerShell) | Linux/Mac (Makefile) |
|------|---------------------|----------------------|
| **Help** | `.\tasks.ps1 help` | `make help` |
| **Install** | `.\tasks.ps1 install` | `make install` |
| **Test** | `.\tasks.ps1 test` | `make test` |
| **Run API** | `.\tasks.ps1 run-api` | `make run-api` |
| **Docker Build** | `.\tasks.ps1 docker-build` | `make docker-build` |
| **Clean** | `.\tasks.ps1 clean` | `make clean` |

---

## 🎯 Typical Workflow

### First Time Setup

```powershell
# 1. Clone repository
git clone https://github.com/Pedrom2002/energy-forecast-pt.git
cd energy-forecast-pt

# 2. Create virtual environment
python -m venv venv
.\venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 3. Install dependencies
.\tasks.ps1 install      # Windows
# make install            # Linux/Mac
```

### Development Cycle

```powershell
# 1. Make code changes
# ... edit files ...

# 2. Format code
.\tasks.ps1 format

# 3. Check code quality
.\tasks.ps1 lint

# 4. Run tests
.\tasks.ps1 test

# 5. If all passes, commit
git add .
git commit -m "Your message"
git push
```

### Testing API

```powershell
# Terminal 1: Start API
.\tasks.ps1 run-api

# Terminal 2: Test endpoints
.\tasks.ps1 test-api
```

### Docker Workflow

```powershell
# 1. Build image
.\tasks.ps1 docker-build

# 2. Run container
.\tasks.ps1 docker-run

# 3. Check logs
.\tasks.ps1 docker-logs

# 4. Stop when done
.\tasks.ps1 docker-stop
```

---

## 🔧 Troubleshooting

### "tasks.ps1 cannot be loaded"

**Solution:** Change execution policy

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### "make: command not found" on Windows

**Solution:** Use `tasks.ps1` instead of `make`

```powershell
# Instead of: make test
.\tasks.ps1 test
```

### "docker: command not found"

**Solution:** Install Docker Desktop first
- Download: https://www.docker.com/products/docker-desktop/

---

## 📚 What Each Command Does

### Development Commands

- **install**: Installs all Python dependencies from `requirements.txt` plus development tools (pytest, black, flake8, isort)
- **test**: Runs all tests with code coverage report (generates HTML report in `htmlcov/`)
- **test-quick**: Runs tests without coverage (faster for quick checks)
- **lint**: Checks code style and quality without making changes
- **format**: Automatically formats code with black and sorts imports with isort

### Docker Commands

- **docker-build**: Creates Docker image tagged as `energy-forecast-api:latest`
- **docker-run**: Starts container in detached mode on port 8000
- **docker-stop**: Stops and removes the container
- **docker-logs**: Shows real-time container logs (Ctrl+C to exit)
- **compose-up**: Starts all services defined in `docker-compose.yml`
- **compose-down**: Stops all docker-compose services

### API Commands

- **run-api**: Starts uvicorn development server with auto-reload on port 8000
- **test-api**: Runs `test_api.ps1` script to test all API endpoints

### Other Commands

- **jupyter**: Opens Jupyter notebook in the `notebooks/` directory
- **deploy-aws/azure/gcp**: Executes deployment scripts for cloud providers
- **clean**: Removes all Python cache files, build artifacts, and test coverage reports

---

## 💡 Tips

1. **Always activate virtual environment first:**
   ```powershell
   .\venv\Scripts\activate
   ```

2. **Run tests before committing:**
   ```powershell
   .\tasks.ps1 test
   ```

3. **Format code automatically:**
   ```powershell
   .\tasks.ps1 format
   ```

4. **Check API is working:**
   ```powershell
   .\tasks.ps1 run-api
   # Visit: http://localhost:8000/docs
   ```

---

## 🆘 Need Help?

```powershell
# Show all available commands
.\tasks.ps1 help
```

Or check the documentation:
- **[README.md](README.md)** - Project overview
- **[docs/](docs/)** - Detailed documentation
- **[DEPLOYMENT.md](docs/DEPLOYMENT.md)** - Deployment guide
