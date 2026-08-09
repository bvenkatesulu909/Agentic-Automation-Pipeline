# Contributing to LangGraph HITL State Manager

Thank you for your interest in contributing to the HITL State Manager! This document provides guidelines for developers wanting to enhance, fix, or extend this contribution.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Development Setup](#development-setup)
3. [Code Guidelines](#code-guidelines)
4. [Testing Requirements](#testing-requirements)
5. [Commit & PR Process](#commit--pr-process)
6. [Adding New Features](#adding-new-features)
7. [Documentation Standards](#documentation-standards)

---

## Getting Started

### Prerequisites

- Python 3.8+
- LangGraph 0.1.0+
- pytest for testing
- Black for code formatting
- mypy for type checking (recommended)

### Project Structure

```
src/langgraph_hitl_contrib/
├── __init__.py                  # Package exports
├── state_manager.py             # Core state management
├── checkpoint_restorer.py        # Checkpoint operations
├── docs/
│   ├── HITL_CONTRIBUTION.md     # User documentation
│   ├── HITL_STATE_MANAGER_GUIDE.md
│   └── __init__.py
├── examples/
│   ├── hitl_resume_example.py   # Complete workflow example
│   ├── hitl_advanced_example.py # Advanced features demo
│   └── __init__.py
├── tests/
│   ├── test_state_manager.py    # Core functionality tests
│   ├── conftest.py              # Test configuration
│   └── __init__.py
└── CONTRIBUTING.md              # This file
```

---

## Development Setup

### 1. Clone and Install

```bash
# Clone repository
git clone https://github.com/your-org/langgraph-hitl.git
cd langgraph-hitl

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -e ".[dev]"
```

### 2. Install Pre-commit Hooks (Optional)

```bash
pip install pre-commit
pre-commit install
```

### 3. Run Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src/langgraph_hitl_contrib

# Run specific test file
pytest tests/test_state_manager.py -v
```

---

## Code Guidelines

### Style & Formatting

**Code Style**: Follow PEP 8 with the following conventions:

```python
# Use Black for formatting
black src/langgraph_hitl_contrib/

# Check with flake8
flake8 src/langgraph_hitl_contrib/

# Type check (recommended)
mypy src/langgraph_hitl_contrib/
```

### Type Hints

All functions must include type hints:

```python
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime

def process_checkpoint(
    checkpoint_id: str,
    state_data: Dict[str, Any],
    validation_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    Process a checkpoint with optional validation.
    
    Args:
        checkpoint_id: Unique checkpoint identifier
        state_data: The state dictionary to process
        validation_fn: Optional validation function
        
    Returns:
        Processed state dictionary
    """
    pass
```

### Docstrings

Use Google-style docstrings:

```python
def create_checkpoint(
    workflow_id: str,
    node_name: str,
    state_snapshot: Dict[str, Any],
) -> CheckpointRecord:
    """
    Create a checkpoint for workflow state persistence.
    
    This method creates a checkpoint at a workflow node, capturing the complete
    state for later restoration. Checkpoints are useful for human-in-the-loop
    workflows where execution may be paused for review.
    
    Args:
        workflow_id: Unique identifier for the workflow
        node_name: Name of the current workflow node
        state_snapshot: Dictionary containing the complete workflow state
        
    Returns:
        CheckpointRecord: The created checkpoint with metadata
        
    Raises:
        ValueError: If workflow_id is empty or invalid
        TypeError: If state_snapshot is not a dictionary
        
    Example:
        >>> checkpoint = manager.create_checkpoint(
        ...     workflow_id="wf_123",
        ...     node_name="approval",
        ...     state_snapshot={"key": "value"}
        ... )
        >>> print(checkpoint.checkpoint_id)
    """
```

### Logging

Use the module logger consistently:

```python
import logging

logger = logging.getLogger(__name__)

def my_function():
    logger.debug("Detailed debug information")
    logger.info("General information")
    logger.warning("Warning message")
    logger.error("Error occurred", exc_info=True)
```

### Error Handling

Raise appropriate exceptions with descriptive messages:

```python
def restore_workflow(self, workflow_id: str) -> HITLWorkflowState:
    """Restore a workflow by ID."""
    if not workflow_id:
        raise ValueError("workflow_id cannot be empty")
    
    if workflow_id not in self._workflows:
        raise ValueError(
            f"Workflow {workflow_id} not found. "
            f"Available workflows: {list(self._workflows.keys())}"
        )
    
    try:
        workflow = self._workflows[workflow_id]
        logger.info(f"Restored workflow {workflow_id}")
        return workflow
    except KeyError as e:
        logger.error(f"Unexpected error restoring workflow: {e}", exc_info=True)
        raise RuntimeError(f"Failed to restore workflow {workflow_id}") from e
```

---

## Testing Requirements

### Writing Tests

All new code must include tests. Use pytest:

```python
import pytest
from langgraph_hitl_contrib import HITLStateManager, WorkflowStatus

class TestCheckpointCreation:
    """Test suite for checkpoint creation."""
    
    @pytest.fixture
    def manager(self):
        """Create a fresh manager for each test."""
        return HITLStateManager()
    
    def test_create_checkpoint_success(self, manager):
        """Test successful checkpoint creation."""
        checkpoint = manager.create_checkpoint(
            workflow_id="wf_123",
            node_name="test_node",
            state_snapshot={"key": "value"}
        )
        
        assert checkpoint.checkpoint_id is not None
        assert checkpoint.workflow_id == "wf_123"
        assert checkpoint.node_name == "test_node"
        assert checkpoint.state_snapshot == {"key": "value"}
    
    def test_create_checkpoint_empty_workflow_id(self, manager):
        """Test that empty workflow_id raises ValueError."""
        with pytest.raises(ValueError):
            manager.create_checkpoint(
                workflow_id="",
                node_name="test_node",
                state_snapshot={"key": "value"}
            )
    
    def test_create_checkpoint_invalid_state(self, manager):
        """Test that non-dict state raises TypeError."""
        with pytest.raises(TypeError):
            manager.create_checkpoint(
                workflow_id="wf_123",
                node_name="test_node",
                state_snapshot="not a dict"
            )
```

### Test Coverage

- **Unit Tests**: Test individual methods in isolation
- **Integration Tests**: Test interactions between components
- **Edge Cases**: Test boundary conditions and error paths
- **Performance Tests**: For optimization-critical operations

Minimum coverage target: **85%**

```bash
# Check coverage
pytest tests/ --cov=src/langgraph_hitl_contrib --cov-report=html
```

### Test Organization

```
tests/
├── __init__.py
├── conftest.py                          # Shared fixtures
├── test_state_manager.py                # Core state manager tests
├── test_checkpoint_restorer.py          # Checkpoint restorer tests
├── test_integration.py                  # Integration tests
├── test_storage_backends.py             # Backend tests
├── test_recovery.py                     # Crash recovery tests
└── fixtures/
    ├── sample_workflows.py              # Test workflow definitions
    └── mock_storage.py                  # Mock storage backend
```

---

## Commit & PR Process

### Branch Naming

Use descriptive branch names:

```bash
# Feature branch
git checkout -b feature/checkpoint-streaming

# Bug fix branch
git checkout -b fix/state-hash-validation

# Enhancement branch
git checkout -b enhance/performance-optimization
```

### Commit Messages

Follow conventional commits:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

**Examples**:
```
feat(state-manager): add what-if scenario execution

Implement execute_what_if_scenario() method to support testing
alternative execution paths without modifying original workflow state.

Fixes: #123
```

```
fix(checkpoint-restorer): resolve state hash validation

Correct computation of state hash to handle non-JSON-serializable
objects properly.

Fixes: #456
```

### Pull Request Process

1. **Create Feature Branch**
   ```bash
   git checkout -b feature/your-feature
   ```

2. **Make Changes**
   - Write code following guidelines
   - Add comprehensive tests
   - Update documentation

3. **Run Tests & Checks**
   ```bash
   pytest tests/ -v
   black src/
   flake8 src/
   mypy src/
   ```

4. **Commit Changes**
   ```bash
   git add .
   git commit -m "feat: description of changes"
   ```

5. **Push and Create PR**
   ```bash
   git push origin feature/your-feature
   # Then create PR on GitHub
   ```

6. **PR Checklist**
   - [ ] Tests added/updated
   - [ ] Documentation updated
   - [ ] Code follows style guidelines
   - [ ] Commit messages follow conventions
   - [ ] No breaking changes (document if unavoidable)
   - [ ] Performance impact considered
   - [ ] Security reviewed (if applicable)

### Code Review Process

**Reviewers will check**:
- ✅ Code quality and style compliance
- ✅ Test coverage and test quality
- ✅ Documentation completeness
- ✅ Type safety
- ✅ Performance implications
- ✅ Security considerations
- ✅ Breaking changes

**Address feedback**:
```bash
# Make requested changes
# Commit with descriptive message
git commit -m "refactor: address review comments"

# Push updates
git push origin feature/your-feature

# DO NOT force push unless specifically requested
```

---

## Adding New Features

### Feature Proposal Process

1. **Open an Issue**
   - Describe the feature
   - Explain use case and benefit
   - Provide examples if possible

2. **Design Discussion**
   - Review feedback from maintainers
   - Iterate on design if needed
   - Get approval before implementation

3. **Implementation**
   - Follow guidelines in this document
   - Include comprehensive tests
   - Update documentation

### Example: Adding a New Query Method

**Step 1: Define the Method**

```python
# In checkpoint_restorer.py

def get_checkpoints_by_metadata(
    self,
    workflow_id: str,
    metadata_filter: Dict[str, Any],
) -> List[CheckpointRecord]:
    """
    Get checkpoints matching metadata criteria.
    
    Args:
        workflow_id: The workflow ID
        metadata_filter: Dict of metadata key/value pairs to match
        
    Returns:
        List of matching checkpoints
        
    Example:
        >>> restorer.get_checkpoints_by_metadata(
        ...     "wf_123",
        ...     {"priority": "high", "source": "api"}
        ... )
    """
    history = self.state_manager.get_workflow_history(workflow_id)
    
    matches = []
    for cp in history:
        if all(
            cp.metadata.get(k) == v
            for k, v in metadata_filter.items()
        ):
            matches.append(cp)
    
    return matches
```

**Step 2: Write Tests**

```python
# In tests/test_checkpoint_restorer.py

def test_get_checkpoints_by_metadata(manager, restorer):
    """Test filtering checkpoints by metadata."""
    # Create checkpoints with different metadata
    manager.create_checkpoint(
        workflow_id="wf_123",
        node_name="node1",
        state_snapshot={},
        metadata={"priority": "high", "source": "api"}
    )
    
    manager.create_checkpoint(
        workflow_id="wf_123",
        node_name="node2",
        state_snapshot={},
        metadata={"priority": "low", "source": "ui"}
    )
    
    # Test query
    results = restorer.get_checkpoints_by_metadata(
        "wf_123",
        {"priority": "high"}
    )
    
    assert len(results) == 1
    assert results[0].node_name == "node1"
```

**Step 3: Update Documentation**

```markdown
#### `get_checkpoints_by_metadata()`

Get checkpoints matching specific metadata criteria.

**Example**:
```python
# Get all high-priority API checkpoints
high_priority = restorer.get_checkpoints_by_metadata(
    workflow_id="workflow_123",
    metadata_filter={"priority": "high", "source": "api"}
)
```

**Step 4: Update CHANGELOG**

```
## [Unreleased]

### Added
- `CheckpointRestorer.get_checkpoints_by_metadata()` for metadata-based filtering
```

---

## Documentation Standards

### API Documentation

Every public method must have:

1. **Docstring** with description, args, returns, exceptions, example
2. **Type hints** on all parameters and return value
3. **Example usage** in docstring

### User Guides

For new features, add to appropriate guide:

1. **HITL_CONTRIBUTION.md** - User-facing documentation
2. **HITL_STATE_MANAGER_GUIDE.md** - Implementation details
3. **Examples** - Concrete working examples

### README Updates

Update repository README with:
- New feature description
- Link to relevant documentation
- Example usage snippet

### Changelog

Maintain CHANGELOG.md with:
- Version number
- Date
- Added/Changed/Fixed/Removed sections

---

## Architecture Decision Records (ADR)

For significant changes, create an ADR:

```
docs/adr/
├── 0001-checkpoint-integrity-verification.md
├── 0002-crash-recovery-strategy.md
└── ...
```

**Format**:
```markdown
# ADR-XXX: Title

## Context
Problem statement and background

## Decision
What we decided to do

## Rationale
Why we made this decision

## Consequences
Implications of this decision
```

---

## Performance & Optimization

### Performance Considerations

When making changes, consider:

1. **Checkpoint creation**: Should be fast (< 50ms)
2. **Workflow restoration**: Should be fast (< 50ms)
3. **State comparison**: O(n) where n = state size
4. **Storage queries**: Use indexes for common filters

### Adding Performance Tests

```python
import pytest
import time

def test_checkpoint_creation_performance():
    """Benchmark checkpoint creation."""
    manager = HITLStateManager()
    large_state = {f"key_{i}": f"value_{i}" for i in range(10000)}
    
    start = time.time()
    manager.create_checkpoint(
        workflow_id="wf_123",
        node_name="perf_test",
        state_snapshot=large_state
    )
    elapsed = time.time() - start
    
    # Should complete in reasonable time
    assert elapsed < 0.1, f"Checkpoint creation took {elapsed}s"
```

---

## Getting Help

- **Questions**: Open a GitHub Discussion
- **Bugs**: Open a GitHub Issue
- **Design Feedback**: Email maintainers
- **Code Review**: Submit a PR

---

## License

By contributing, you agree that your contributions will be licensed under the same terms as the project.

---

## Code of Conduct

This project adheres to the Contributor Covenant Code of Conduct. By participating, you are expected to uphold this code.

Thank you for contributing to make HITL State Manager better!
