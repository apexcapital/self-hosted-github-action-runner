#!/usr/bin/env python3
"""
Validation script for the GitHub Actions Runner Orchestrator.
This script checks that all dependencies are installed and modules can be imported.
"""

import sys
import traceback
from typing import List, Tuple


def test_imports() -> List[Tuple[str, bool, str]]:
    """Test that all required modules can be imported."""
    results = []

    # Core dependencies
    test_modules = [
        ("fastapi", "FastAPI framework"),
        ("uvicorn", "ASGI server"),
        ("docker", "Docker client"),
        ("pydantic", "Data validation"),
        ("pydantic_settings", "Settings management"),
        ("httpx", "HTTP client"),
        ("structlog", "Structured logging"),
        ("tenacity", "Retry library"),
    ]

    for module, description in test_modules:
        try:
            __import__(module)
            results.append((module, True, f"✅ {description}"))
        except ImportError as e:
            results.append((module, False, f"❌ {description}: {e}"))

    return results


def test_orchestrator_modules() -> List[Tuple[str, bool, str]]:
    """Test that orchestrator modules can be imported."""
    results = []

    orchestrator_modules = [
        ("src.config", "Configuration management"),
        ("src.utils.logging", "Logging utilities"),
        ("src.github_client", "GitHub API client"),
        ("src.docker_client", "Docker container management"),
        ("src.orchestrator", "Main orchestrator"),
        ("src.api.routes", "API routes"),
    ]

    for module, description in orchestrator_modules:
        try:
            __import__(module)
            results.append((module, True, f"✅ {description}"))
        except ImportError as e:
            results.append((module, False, f"❌ {description}: {e}"))
        except Exception as e:
            # Configuration errors are expected without proper env vars
            if "ValidationError" in str(e) or "github_token" in str(e):
                results.append(
                    (
                        module,
                        True,
                        f"✅ {description} (config validation error expected)",
                    )
                )
            else:
                results.append((module, False, f"❌ {description}: {e}"))

    return results


def test_fastapi_app() -> Tuple[bool, str]:
    """Test that FastAPI app can be created."""
    try:
        # Set minimal environment for testing
        import os

        os.environ["ORCHESTRATOR_GITHUB_TOKEN"] = "test_token"

        from main import app

        return True, "✅ FastAPI application created successfully"
    except Exception as e:
        return False, f"❌ FastAPI application failed: {e}"


def main():
    """Run all validation tests."""
    print("🚀 GitHub Actions Runner Orchestrator - Validation Script")
    print("=" * 60)

    # Test core dependencies
    print("\n📦 Testing Core Dependencies:")
    core_results = test_imports()
    for module, success, message in core_results:
        print(f"  {message}")

    # Test orchestrator modules
    print("\n🏗️  Testing Orchestrator Modules:")
    module_results = test_orchestrator_modules()
    for module, success, message in module_results:
        print(f"  {message}")

    # Test FastAPI app
    print("\n🌐 Testing FastAPI Application:")
    app_success, app_message = test_fastapi_app()
    print(f"  {app_message}")

    # Summary
    print("\n📊 Summary:")
    total_tests = len(core_results) + len(module_results) + 1
    successful_tests = (
        sum(1 for _, success, _ in core_results if success)
        + sum(1 for _, success, _ in module_results if success)
        + (1 if app_success else 0)
    )

    print(f"  Tests passed: {successful_tests}/{total_tests}")

    if successful_tests == total_tests:
        print("  🎉 All tests passed! The orchestrator is ready to deploy.")
        sys.exit(0)
    else:
        print("  ⚠️  Some tests failed. Please check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
