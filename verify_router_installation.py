#!/usr/bin/env python3
"""Quick verification that the router is properly installed and working.

Run this to verify:
  python verify_router_installation.py
"""

from __future__ import annotations

import sys
from pathlib import Path


def check_python_version():
    """Verify Python 3.10+."""
    if sys.version_info < (3, 10):
        print(f"❌ Python 3.10+ required (you have {sys.version_info.major}.{sys.version_info.minor})")
        return False
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor} OK")
    return True


def check_imports():
    """Verify core modules can be imported."""
    modules = [
        ("ragstack.router", "Core router module"),
        ("ragstack.metrics", "Prometheus metrics module"),
        ("ragstack.metrics_server", "FastAPI server module"),
    ]

    success = True
    for module_name, description in modules:
        try:
            __import__(module_name)
            print(f"✓ {description} ({module_name})")
        except ImportError as e:
            print(f"❌ {description} ({module_name}): {e}")
            success = False

    return success


def check_router_basic_functionality():
    """Verify router works."""
    try:
        from ragstack.router import (
            ModelRouter,
            preset_anthropic_only,
            estimate_complexity,
        )

        # Test complexity estimation
        score = estimate_complexity("What is AI?")
        assert 0 <= score <= 100, f"Invalid complexity score: {score}"
        print(f"✓ Complexity estimation works (score: {score}/100)")

        # Test routing
        config = preset_anthropic_only()
        router = ModelRouter(config)
        decision = router.route("Test query")

        assert decision.model is not None
        assert 0 <= decision.complexity_score <= 100
        assert decision.estimated_cost >= 0
        print(f"✓ Basic routing works (model: {decision.model.name})")

        return True
    except Exception as e:
        print(f"❌ Router functionality check failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_metrics():
    """Verify metrics collection."""
    try:
        from ragstack.metrics import (
            get_prometheus_text,
            record_query_complexity,
            record_router_decision,
            get_metrics_collector,
        )

        # Reset and record some metrics
        collector = get_metrics_collector()
        collector.reset()

        record_query_complexity(50)
        record_router_decision("cheap", "test-model", 50)

        # Export metrics
        text = get_prometheus_text()
        assert len(text) > 0
        assert "ragstack_query_complexity" in text
        print(f"✓ Metrics collection works ({len(text)} bytes exported)")

        return True
    except Exception as e:
        print(f"❌ Metrics check failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_optional_dependencies():
    """Check for optional dependencies."""
    try:
        import fastapi
        import uvicorn
        import litellm
        print("✓ Optional dependencies (FastAPI, uvicorn, litellm) installed")
        return True
    except ImportError as e:
        print(f"⚠ Optional dependencies not installed: {e}")
        print("  Install with: pip install -e '.[router]'")
        return True  # Not a failure, just optional


def check_file_structure():
    """Verify file structure."""
    files = [
        "src/ragstack/router.py",
        "src/ragstack/metrics.py",
        "src/ragstack/metrics_server.py",
        "src/ragstack/metrics_server_main.py",
        "src/ragstack/router_example.py",
        "tests/test_router.py",
        "ROUTER_README.md",
        "ROUTER_GUIDE.md",
        "ROUTER_INTEGRATION_EXAMPLE.md",
    ]

    success = True
    for file in files:
        path = Path(file)
        if path.exists():
            size = path.stat().st_size
            print(f"✓ {file} ({size} bytes)")
        else:
            print(f"❌ {file} not found")
            success = False

    return success


def main():
    """Run all checks."""
    print("\n" + "=" * 60)
    print("RAGStack Model Router - Installation Verification")
    print("=" * 60 + "\n")

    checks = [
        ("Python Version", check_python_version),
        ("Core Imports", check_imports),
        ("File Structure", check_file_structure),
        ("Router Functionality", check_router_basic_functionality),
        ("Metrics Collection", check_metrics),
        ("Optional Dependencies", check_optional_dependencies),
    ]

    results = []
    for name, check_func in checks:
        print(f"\n{name}:")
        print("-" * 40)
        result = check_func()
        results.append(result)

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} checks passed")
    print("=" * 60)

    if all(results):
        print("\n✓ All checks passed! Router is ready to use.")
        print("\nNext steps:")
        print("  1. Read ROUTER_README.md for quick start")
        print("  2. Run examples: python -m ragstack.router_example")
        print("  3. Start server: python -m ragstack.metrics_server_main")
        print("  4. See ROUTER_INTEGRATION_EXAMPLE.md for integration patterns\n")
        return 0
    else:
        print("\n❌ Some checks failed. See errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
