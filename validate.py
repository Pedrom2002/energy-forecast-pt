#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Validation script to check project health
Runs all tests, linting, and validation checks
"""

import subprocess
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')


def run_command(cmd, description):
    """Run a command and print results"""
    print(f"\n{'='*60}")
    print(f"🔍 {description}")
    print(f"{'='*60}")

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"✅ {description} - PASSED")
        if result.stdout:
            print(result.stdout)
        return True
    else:
        print(f"❌ {description} - FAILED")
        if result.stderr:
            print(result.stderr)
        if result.stdout:
            print(result.stdout)
        return False


def main():
    """Run all validation checks"""
    print("\n" + "="*60)
    print("🚀 ENERGY FORECAST PT - VALIDATION SUITE")
    print("="*60)

    checks = []

    # 1. Check if required files exist
    print("\n📁 Checking project structure...")
    required_files = [
        "requirements.txt",
        "Dockerfile",
        "docker-compose.yml",
        "pytest.ini",
        "src/api/main.py",
        "src/features/feature_engineering.py",
        "src/models/evaluation.py",
    ]

    missing_files = []
    for file in required_files:
        if not Path(file).exists():
            missing_files.append(file)

    if missing_files:
        print(f"❌ Missing files: {', '.join(missing_files)}")
        checks.append(False)
    else:
        print("✅ All required files present")
        checks.append(True)

    # 2. Run pytest
    checks.append(run_command(
        "python -m pytest tests/ -v --tb=short",
        "Running pytest"
    ))

    # 3. Check if models exist
    print("\n📦 Checking trained models...")
    model_path = Path("data/models")
    if model_path.exists():
        models = list(model_path.glob("*.pkl"))
        if models:
            print(f"✅ Found {len(models)} trained models")
            checks.append(True)
        else:
            print("⚠️  No trained models found")
            checks.append(False)
    else:
        print("❌ Models directory not found")
        checks.append(False)

    # 4. Validate API imports
    checks.append(run_command(
        "python -c \"from src.api.main import app; print('API imports OK')\"",
        "Validating API imports"
    ))

    # 5. Check Docker files
    print("\n🐳 Checking Docker configuration...")
    docker_checks = []

    # Check Dockerfile
    with open("Dockerfile", 'r') as f:
        dockerfile = f.read()
        if "COPY test_api.py" in dockerfile:
            print("❌ Dockerfile references non-existent test_api.py")
            docker_checks.append(False)
        else:
            print("✅ Dockerfile looks good")
            docker_checks.append(True)

    # Check docker-compose
    with open("docker-compose.yml", 'r') as f:
        compose = f.read()
        if "curl" in compose and "CMD" in compose:
            print("⚠️  docker-compose may use curl (not installed in container)")
            docker_checks.append(False)
        else:
            print("✅ docker-compose looks good")
            docker_checks.append(True)

    checks.append(all(docker_checks))

    # 6. Check CI/CD workflow
    print("\n🔄 Checking CI/CD workflow...")
    workflow_file = Path(".github/workflows/ci-cd.yml")
    if workflow_file.exists():
        print("✅ CI/CD workflow file found")
        checks.append(True)
    else:
        print("❌ CI/CD workflow not found")
        checks.append(False)

    # 7. Check deployment scripts
    print("\n☁️  Checking deployment scripts...")
    deploy_scripts = ["deploy/deploy-aws.sh", "deploy/deploy-azure.sh", "deploy/deploy-gcp.sh"]
    deploy_ok = all(Path(script).exists() for script in deploy_scripts)

    if deploy_ok:
        print(f"✅ All {len(deploy_scripts)} deployment scripts found")
        checks.append(True)
    else:
        print("❌ Some deployment scripts missing")
        checks.append(False)

    # Summary
    print("\n" + "="*60)
    print("📊 VALIDATION SUMMARY")
    print("="*60)

    passed = sum(checks)
    total = len(checks)
    percentage = (passed / total) * 100

    print(f"\n✅ Passed: {passed}/{total} ({percentage:.1f}%)")
    print(f"❌ Failed: {total - passed}/{total}")

    if passed == total:
        print("\n🎉 All checks passed! Project is healthy!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} check(s) failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
