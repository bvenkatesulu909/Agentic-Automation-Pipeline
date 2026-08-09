# Contributing to CrewAI Tool Execution Tracer

Thank you for your interest in contributing to the CrewAI Tool Execution Tracer! This document provides guidelines and instructions for contributing code, documentation, and improvements.

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Development Setup](#development-setup)
3. [Making Changes](#making-changes)
4. [Code Style and Standards](#code-style-and-standards)
5. [Testing Requirements](#testing-requirements)
6. [Adding New Exporters](#adding-new-exporters)
7. [Documentation Guidelines](#documentation-guidelines)
8. [Commit Conventions](#commit-conventions)
9. [Pull Request Workflow](#pull-request-workflow)
10. [Review Process](#review-process)

---

## Code of Conduct

This project adheres to a Contributor Code of Conduct. By participating, you are expected to:

- Be respectful and inclusive
- Accept constructive criticism
- Focus on collaborative problem-solving
- Report inappropriate behavior to maintainers

---

## Development Setup

### Prerequisites

- Python 3.8+
- pip and virtual environments
- Git

### Local Development Environment

```bash
# Clone the repository
git clone https://github.com/your-username/crewai-tool-tracer.git
cd crewai-tool-tracer

# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install development dependencies
pip install -e ".[dev]"

# Install testing and linting tools
pip install pytest pytest-cov pytest-asyncio
pip install black flake8 isort mypy
pip install sphinx sphinx-rtd-theme
```

### Project Structure

```
src/crewai_tool_tracer/
├── __init__.py                      # Package exports
├── tracer.py                        # Core tracer class
├── async_tracer.py                  # Async support
├── decorators.py                    # Decorator utilities
├── exporters.py                     # Export backends
├── structured_logging.py            # Logging system
├── integration.py                   # CrewAI integration
├── docs/                            # Documentation
│   ├── TOOL_TRACER_CONTRIBUTION.md # Main docs
│   ├── CREWAI_INTEGRATION_GUIDE.md  # Integration guide
│   └── API_REFERENCE.md            # API reference
├── examples/                        # Usage examples
│   ├── tool_tracer_example.py
│   ├── comprehensive_crewai_example.py
│   └── crewai_complete_integration.py
├── tests/                           # Test suite
│   ├── test_tracer.py              # Main tests
│   ├── test_benchmarks.py          # Performance tests
│   └── pytest.ini
└── CONTRIBUTING.md                  # This file
```

---

## Making Changes

### General Workflow

1. Fork the repository on GitHub
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Add/update tests
5. Ensure code passes linting and tests
6. Commit with clear messages
7. Push to your fork
8. Create a pull request

### Creating a Feature Branch

```bash
# From main branch
git checkout main
git pull origin main

# Create feature branch with descriptive name
git checkout -b feature/add-prometheus-exporter
```

### Working on Code

#### For Bug Fixes

```bash
# Branch name format: fix/description
git checkout -b fix/span-rotation-bug

# Make changes to fix the bug
# Write test that reproduces the bug
# Verify test passes
```

#### For New Features

```bash
# Branch name format: feature/description
git checkout -b feature/prometheus-exporter

# Implement feature
# Add comprehensive tests
# Update documentation
```

#### For Documentation

```bash
# Branch name format: docs/description
git checkout -b docs/add-benchmarking-guide

# Update or create documentation
# Verify formatting
```

---

## Code Style and Standards

### Python Code Style

We use Black for code formatting and follow PEP 8 conventions.

#### Formatting with Black

```bash
# Format all Python files
black src/crewai_tool_tracer/

# Format specific file
black src/crewai_tool_tracer/tracer.py
```

#### Import Organization with isort

```bash
# Organize imports
isort src/crewai_tool_tracer/

# Verify import organization
isort --check-only src/crewai_tool_tracer/
```

### Code Quality Checks

#### Linting with flake8

```bash
# Run flake8
flake8 src/crewai_tool_tracer/ --max-line-length=100

# Common issues:
# - E501: Line too long (should be <100 chars)
# - W503: Line break before binary operator
# - F841: Local variable assigned but never used
```

#### Type Checking with mypy

```bash
# Run type checking
mypy src/crewai_tool_tracer/ --ignore-missing-imports

# Verify type annotations are correct
```

### Code Style Guide

#### Naming Conventions

```python
# ✅ GOOD: Classes use PascalCase
class ToolExecutionTracer:
    pass

class DatadogExporter:
    pass

# ✅ GOOD: Functions use snake_case
def trace_tool_call():
    pass

def get_tool_metrics():
    pass

# ✅ GOOD: Constants use UPPER_SNAKE_CASE
MAX_SPANS = 10000
DEFAULT_TIMEOUT_MS = 5000

# ❌ BAD: Inconsistent naming
class toolTracer:
    pass

def getTool_Metrics():
    pass
```

#### Docstring Format

```python
# ✅ GOOD: Google-style docstrings
def trace_tool_call(
    self,
    tool_name: str,
    input_data: Dict[str, Any],
    agent_name: str,
    task_name: str,
) -> str:
    """
    Start tracing a tool call.

    Creates a new span to track the execution of a tool within
    a CrewAI agent and task context.

    Args:
        tool_name: Name of the tool being called
        input_data: Input dictionary for the tool
        agent_name: Name of the agent executing the tool
        task_name: Name of the task context

    Returns:
        str: Unique span ID for this execution

    Raises:
        ValueError: If span_id is invalid

    Example:
        >>> tracer = ToolExecutionTracer(name="my-crew")
        >>> span_id = tracer.trace_tool_call(
        ...     tool_name="search",
        ...     input_data={"query": "AI"},
        ...     agent_name="researcher",
        ...     task_name="research",
        ... )
    """
```

#### Type Annotations

```python
# ✅ GOOD: Complete type annotations
from typing import Dict, Any, Optional, List, Tuple

def get_tool_metrics(
    self,
    time_range: Optional[Tuple[datetime, datetime]] = None,
    tool_name: Optional[str] = None,
    agent_name: Optional[str] = None,
) -> ToolMetrics:
    """Get aggregated metrics."""
    pass

# ❌ BAD: Missing type annotations
def get_tool_metrics(self, time_range=None, tool_name=None):
    """Get aggregated metrics."""
    pass
```

#### Line Length

- Maximum line length: 100 characters
- Use line continuation for long lines

```python
# ✅ GOOD: Line continuation
spans_to_export = [
    s for s in self._spans.values()
    if s.duration_ms > threshold
]

# ❌ BAD: Line too long
spans_to_export = [s for s in self._spans.values() if s.duration_ms > threshold and s.status == SpanStatus.SUCCESS and s.tool_name in critical_tools]
```

---

## Testing Requirements

### Test Structure

Tests are located in `src/crewai_tool_tracer/tests/`:

```
tests/
├── test_tracer.py           # Core tracer tests
├── test_benchmarks.py       # Performance tests
├── test_async_tracer.py     # Async functionality
├── test_exporters.py        # Exporter tests
├── test_decorators.py       # Decorator tests
└── pytest.ini               # Pytest configuration
```

### Running Tests

```bash
# Run all tests
pytest src/crewai_tool_tracer/tests/ -v

# Run specific test file
pytest src/crewai_tool_tracer/tests/test_tracer.py -v

# Run specific test class
pytest src/crewai_tool_tracer/tests/test_tracer.py::TestToolExecutionTracer -v

# Run specific test method
pytest src/crewai_tool_tracer/tests/test_tracer.py::TestToolExecutionTracer::test_trace_tool_call -v

# Run with coverage
pytest src/crewai_tool_tracer/tests/ --cov=src/crewai_tool_tracer --cov-report=html

# Run async tests
pytest src/crewai_tool_tracer/tests/ -v -k "async"
```

### Test Coverage Requirements

- Minimum coverage: 80%
- New features must have >90% coverage
- Bug fixes must include regression test

```bash
# Check current coverage
pytest src/crewai_tool_tracer/tests/ --cov=src/crewai_tool_tracer --cov-report=term-missing

# Generate HTML coverage report
pytest src/crewai_tool_tracer/tests/ --cov=src/crewai_tool_tracer --cov-report=html
# View in: htmlcov/index.html
```

### Writing Tests

#### Test Template

```python
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.crewai_tool_tracer.tracer import (
    ToolExecutionTracer,
    ToolSpan,
    SpanStatus,
)


class TestNewFeature:
    """Tests for new feature."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tracer = ToolExecutionTracer(name="test-tracer")

    def teardown_method(self):
        """Clean up after tests."""
        self.tracer.clear_spans()

    def test_feature_success(self):
        """Test feature works correctly."""
        # Setup
        span_id = self.tracer.trace_tool_call(
            tool_name="test_tool",
            input_data={"key": "value"},
            agent_name="test_agent",
            task_name="test_task",
        )

        # Execute
        self.tracer.record_tool_result(
            span_id=span_id,
            result={"status": "success"},
            duration_ms=100.0,
            success=True,
        )

        # Verify
        span = self.tracer.get_span(span_id)
        assert span is not None
        assert span.status == SpanStatus.SUCCESS
        assert span.result == {"status": "success"}

    def test_feature_error_handling(self):
        """Test feature handles errors correctly."""
        # Setup & Execute
        span_id = self.tracer.trace_tool_call(
            tool_name="test_tool",
            input_data={},
            agent_name="test_agent",
            task_name="test_task",
        )

        error = ValueError("Test error")
        self.tracer.record_tool_result(
            span_id=span_id,
            result=None,
            duration_ms=50.0,
            success=False,
            error=error,
        )

        # Verify
        span = self.tracer.get_span(span_id)
        assert span.status == SpanStatus.ERROR
        assert span.error_message == "Test error"

    @pytest.mark.asyncio
    async def test_async_feature(self):
        """Test async feature."""
        # Setup for async test
        pass
```

#### Testing Decorators

```python
def test_traced_tool_decorator():
    """Test @traced_tool decorator."""
    from crewai_tool_tracer.decorators import traced_tool

    tracer = ToolExecutionTracer(name="test")

    @traced_tool(tracer, agent_name="agent", task_name="task")
    def sample_tool(x):
        return x * 2

    # Execute
    result = sample_tool(5)

    # Verify
    assert result == 10
    spans = tracer.get_all_spans()
    assert len(spans) == 1
    assert spans[0].tool_name == "sample_tool"
    assert spans[0].status == SpanStatus.SUCCESS
```

#### Testing Exporters

```python
@patch('requests.post')
def test_datadog_exporter_success(self, mock_post):
    """Test Datadog exporter."""
    mock_post.return_value = Mock(status_code=200)

    exporter = DatadogExporter(api_key="test-key")
    spans = [self.create_test_span()]

    result = exporter.export(spans)

    assert result is True
    mock_post.assert_called_once()
```

---

## Adding New Exporters

### Exporter Template

```python
"""
Custom exporter for [Platform Name].

Provides integration with [Platform] for exporting tool execution traces.
"""

import os
from typing import List, Optional
import logging

from .tracer import ToolSpan, SpanStatus
from .exporters import BaseExporter

logger = logging.getLogger(__name__)


class CustomExporter(BaseExporter):
    """
    Exporter for [Platform Name].

    Converts CrewAI tool execution spans into [Platform] trace format
    and sends them to the [Platform] API.

    Example:
        >>> from crewai_tool_tracer import CustomExporter
        >>> exporter = CustomExporter(api_key="your-api-key")
        >>> exporter.export(tracer.get_all_spans())
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        service_name: str = "crewai-tools",
    ):
        """
        Initialize [Platform] exporter.

        Args:
            api_key: API key for [Platform] (defaults to env var)
            endpoint: Custom endpoint URL (defaults to [Platform] standard)
            service_name: Service name for traces
        """
        self.api_key = api_key or os.getenv("CUSTOM_API_KEY")
        self.endpoint = endpoint or "https://api.custom.com/v1/traces"
        self.service_name = service_name

        if not self.api_key:
            logger.warning("[Platform] API key not configured")

    def export(self, spans: List[ToolSpan]) -> bool:
        """
        Export spans to [Platform].

        Args:
            spans: List of ToolSpan objects to export

        Returns:
            bool: True if export successful, False otherwise
        """
        if not self.api_key:
            logger.error("[Platform] API key is required")
            return False

        try:
            traces = self._convert_to_custom_format(spans)
            return self._send_traces(traces)
        except Exception as e:
            logger.error(f"Failed to export to [Platform]: {e}")
            return False

    def _convert_to_custom_format(self, spans: List[ToolSpan]) -> dict:
        """Convert spans to [Platform] format."""
        return {
            "service": self.service_name,
            "traces": [self._span_to_trace(span) for span in spans],
        }

    def _span_to_trace(self, span: ToolSpan) -> dict:
        """Convert single span to trace format."""
        return {
            "id": span.span_id,
            "name": span.tool_name,
            "tags": {
                "agent": span.agent_name,
                "task": span.task_name,
                "status": span.status.value,
                **span.tags,
            },
            "duration_ms": span.duration_ms,
            "timestamp": span.start_time.isoformat() if span.start_time else None,
            "error": span.error_message,
        }

    def _send_traces(self, traces: dict) -> bool:
        """Send traces to [Platform] API."""
        try:
            import requests

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            response = requests.post(
                self.endpoint,
                json=traces,
                headers=headers,
                timeout=10,
            )

            if response.status_code in [200, 202]:
                logger.info(f"Exported {len(traces['traces'])} spans to [Platform]")
                return True
            else:
                logger.error(f"[Platform] API error: {response.status_code}")
                return False

        except ImportError:
            logger.error("requests library required. Install with: pip install requests")
            return False
        except Exception as e:
            logger.error(f"Failed to send traces: {e}")
            return False
```

### Steps to Add New Exporter

1. Create exporter class inheriting from `BaseExporter`
2. Implement `export()` method
3. Add unit tests in `tests/test_exporters.py`
4. Update `__init__.py` to export new class
5. Add documentation example
6. Update `CONTRIBUTING.md` if needed

### Testing New Exporter

```python
# Add to tests/test_exporters.py

class TestCustomExporter:
    """Tests for CustomExporter."""

    def setup_method(self):
        """Set up test fixtures."""
        self.exporter = CustomExporter(api_key="test-key")
        self.tracer = ToolExecutionTracer(name="test")

    @patch('requests.post')
    def test_export_success(self, mock_post):
        """Test successful export."""
        mock_post.return_value = Mock(status_code=200)

        spans = self._create_test_spans()
        result = self.exporter.export(spans)

        assert result is True
        mock_post.assert_called_once()

    @patch('requests.post')
    def test_export_failure(self, mock_post):
        """Test export failure."""
        mock_post.return_value = Mock(status_code=500)

        spans = self._create_test_spans()
        result = self.exporter.export(spans)

        assert result is False

    def _create_test_spans(self):
        """Create test spans."""
        span_id = self.tracer.trace_tool_call(
            tool_name="test",
            input_data={},
            agent_name="agent",
            task_name="task",
        )
        self.tracer.record_tool_result(
            span_id=span_id,
            result={"status": "ok"},
            duration_ms=100,
            success=True,
        )
        return self.tracer.get_all_spans()
```

---

## Documentation Guidelines

### Writing Documentation

1. Use clear, concise language
2. Include practical examples
3. Cover both basic and advanced use cases
4. Keep code examples up-to-date
5. Update documentation with code changes

### Documentation Sections

```markdown
# Feature Name

## Overview
Brief description of the feature and its purpose.

## Prerequisites
What's needed to use this feature.

## Basic Usage
Simple example to get started.

## Advanced Usage
More complex scenarios and options.

## API Reference
Complete API documentation.

## Examples
Real-world usage examples.

## Troubleshooting
Common issues and solutions.

## See Also
Links to related documentation.
```

### Code Examples in Documentation

```python
# ✅ GOOD: Runnable, tested examples
from crewai_tool_tracer import ToolExecutionTracer

tracer = ToolExecutionTracer(name="my-crew")
span_id = tracer.trace_tool_call(
    tool_name="search",
    input_data={"query": "AI"},
    agent_name="researcher",
    task_name="research",
)
```

---

## Commit Conventions

### Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- **feat**: A new feature
- **fix**: A bug fix
- **docs**: Documentation changes
- **style**: Code style changes (formatting)
- **refactor**: Code refactoring without feature changes
- **perf**: Performance improvements
- **test**: Adding or updating tests
- **chore**: Build process, dependencies, etc.

### Scopes

- **tracer**: Core tracer functionality
- **exporters**: Export backends
- **decorators**: Decorator utilities
- **integration**: CrewAI integration
- **logging**: Structured logging
- **tests**: Test suite
- **docs**: Documentation

### Example Commits

```bash
# Feature commit
git commit -m "feat(exporters): add Prometheus exporter support"

# Bug fix commit
git commit -m "fix(tracer): correct span rotation logic

Previously, oldest spans were incorrectly identified,
causing recent spans to be removed instead.

Fixes #123"

# Documentation commit
git commit -m "docs: add performance benchmarking guide"

# Test commit
git commit -m "test(exporters): add comprehensive Datadog exporter tests"
```

### Commit Message Guidelines

- Use imperative mood: "add feature" not "added feature"
- Don't capitalize first line
- Limit first line to 50 characters
- Wrap body at 72 characters
- Reference issues: "Fixes #123" or "Related to #456"
- Explain what and why, not how

---

## Pull Request Workflow

### Before Creating PR

1. Ensure all tests pass: `pytest src/crewai_tool_tracer/tests/ -v`
2. Check code coverage: `pytest --cov=src/crewai_tool_tracer`
3. Run linting: `flake8 src/crewai_tool_tracer/`
4. Format code: `black src/crewai_tool_tracer/`
5. Run type checking: `mypy src/crewai_tool_tracer/`

### Creating a PR

1. Push your feature branch to your fork
2. Create a pull request to the main repository
3. Fill out the PR template completely
4. Link related issues
5. Provide context and rationale

### PR Template

```markdown
## Description
Brief description of changes.

## Related Issues
Fixes #123
Related to #456

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## How to Test
Steps to verify the changes.

## Checklist
- [ ] Tests pass
- [ ] Code is formatted with Black
- [ ] Linting passes
- [ ] Coverage >= 80%
- [ ] Documentation updated
- [ ] Commit messages follow conventions

## Screenshots (if applicable)
Relevant screenshots or outputs.
```

---

## Review Process

### Code Review

Pull requests will be reviewed by maintainers for:

1. **Correctness**: Does the code do what it's supposed to?
2. **Quality**: Is the code well-written and maintainable?
3. **Tests**: Are changes covered by tests?
4. **Documentation**: Is the change documented?
5. **Performance**: Are there any performance implications?
6. **Security**: Are there any security issues?

### Common Feedback

- **"Add a test for this"**: Include test coverage
- **"Update the docs"**: Documentation updates needed
- **"Consider refactoring"**: Code clarity or maintainability issue
- **"Performance concern"**: Potential performance problem
- **"Breaking change"**: This changes the API/behavior

### Addressing Feedback

```bash
# Make changes based on feedback
# Don't force push if possible
git add .
git commit -m "Address review feedback"
git push origin feature/my-feature

# If force push is needed (rare)
git push origin feature/my-feature --force-with-lease
```

### Approval and Merge

- PRs require at least 2 approvals from maintainers
- All CI checks must pass
- No unresolved conversations
- Branch must be up-to-date with main

---

## Resources

- [PEP 8 Style Guide](https://www.python.org/dev/peps/pep-0008/)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- [pytest Documentation](https://docs.pytest.org/)
- [Black Code Formatter](https://black.readthedocs.io/)
- [Type Hints in Python](https://docs.python.org/3/library/typing.html)

---

## Getting Help

- **Questions**: Open a discussion on GitHub
- **Bugs**: Create an issue with reproduction steps
- **Ideas**: Start a discussion before implementing
- **Review**: Tag maintainers for feedback

Thank you for contributing!
