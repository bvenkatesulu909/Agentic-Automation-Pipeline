"""Pytest configuration and shared fixtures.

Integrates the evaluation harness plugin for testing.
"""

import pytest
from pathlib import Path
from typing import Callable

# Import eval plugin to register it
pytest_plugins = ["ragstack.eval.pytest_plugin"]


@pytest.fixture
def rag_executor() -> Callable[[str, str], str]:
    """Fixture providing a basic RAG executor for testing.

    In your tests, you can use this fixture to run evaluations:

    Example:
        def test_eval(rag_executor):
            from ragstack.eval.pytest_plugin import run_golden_test
            result = run_golden_test("fac_001", rag_executor)
            assert result.passed
    """

    def executor(question: str, context: str) -> str:
        """Basic executor that concatenates context and question.

        In production, this would be your actual RAG pipeline.
        """
        if not context or len(context.strip()) == 0:
            return "No relevant context found to answer this question."

        # Simple answer generation (replace with actual RAG pipeline)
        answer_template = f"Based on the provided context, the answer is: {question.split()[-1] if question else 'unknown'}"
        return answer_template

    return executor


@pytest.fixture
def eval_results_dir(tmp_path: Path) -> Path:
    """Fixture providing a temporary directory for eval results."""
    results_dir = tmp_path / "eval_results"
    results_dir.mkdir()
    return results_dir


@pytest.fixture
def sample_rag_executor() -> Callable[[str, str], str]:
    """Fixture providing a more realistic RAG executor mock."""

    def executor(question: str, context: str) -> str:
        """Mock executor that simulates RAG pipeline."""
        try:
            # In a real implementation, this would:
            # 1. Embed the question
            # 2. Retrieve relevant documents
            # 3. Generate an answer using an LLM

            # For testing, we'll simulate a reasonable response
            if not context:
                return "No relevant documents found."

            # Simple heuristic: if question is in context, answer is good
            if question.lower() in context.lower():
                return f"Based on the context: The answer relates to '{question}'."
            else:
                return f"The context doesn't directly address '{question}'."

        except Exception as e:
            return f"Error processing query: {str(e)}"

    return executor


@pytest.fixture(autouse=True)
def reset_eval_cache():
    """Reset any cached state between tests."""
    yield
    # Cleanup if needed


def pytest_configure(config):
    """Configure pytest with eval markers."""
    config.addinivalue_line(
        "markers",
        "eval: evaluation harness tests",
    )
    config.addinivalue_line(
        "markers",
        "eval_slow: slow evaluation tests (skip with -m 'not eval_slow')",
    )
    config.addinivalue_line(
        "markers",
        "eval_regression: regression detection tests",
    )
