# Automated Evaluation Harness - Quick Start Guide

Get started with the production-grade evaluation system for your RAG pipeline in 5 minutes.

## What You Get

✅ **100+ Golden Test Cases** - Comprehensive test coverage  
✅ **Multi-Framework Evaluation** - DeepEval + RAGAS + LangSmith  
✅ **Regression Detection** - Automatic regression blocking  
✅ **Quality Trend Tracking** - Historical metric analysis  
✅ **Pre-Deploy Checks** - CI/CD integration ready  
✅ **Detailed Reports** - HTML and JSON outputs  

## Installation (1 min)

```bash
# Install with evaluation dependencies
pip install -e ".[eval]"

# Verify installation
eval count-cases
# Output: Total golden test cases: 100+
```

## Basic Usage (2 min)

### 1. Run Evaluation Suite

```bash
# Run all 100+ test cases
eval run

# For faster feedback, skip slow tests
eval run --skip-slow

# Run only specific category
eval run --category factual
```

### 2. View Results

Results are saved to `eval_results/` directory:
- `report_YYYYMMDD_HHMMSS.txt` - Human-readable report
- `metrics_YYYYMMDD_HHMMSS.json` - Metric scores
- `eval_results_YYYYMMDD_HHMMSS.json` - Individual test results
- `metric_history.json` - Historical tracking

### 3. Check for Regressions

```bash
# Show quality trends
eval show-trend

# Example output:
# 📈 answer_relevance: 0.845 (+2.1%) [improving]
# → faithfulness: 0.812 (+0.3%) [stable]
# 📉 hallucination_rate: 0.188 (-0.3%) [stable]
```

## Programmatic Usage (2 min)

```python
from ragstack.eval.harness import EvalHarness
from ragstack.pdf_qa.llm_chain import AnswerGenerator

# Step 1: Create a RAG executor
def my_rag_executor(question: str, context: str) -> str:
    """Your actual RAG pipeline."""
    generator = AnswerGenerator()
    from ragstack.pdf_qa.models import RetrievalResult
    
    chunks = [
        RetrievalResult(
            chunk_id="1",
            content=context,
            relevance_score=1.0,
            source="input"
        )
    ]
    response = generator.generate_answer(question, chunks)
    return response.answer

# Step 2: Initialize harness
harness = EvalHarness(
    rag_executor=my_rag_executor,
    results_dir="eval_results",
    regression_threshold=5.0,  # Block on 5%+ regression
)

# Step 3: Run evaluation
harness.run_all_tests(max_tests=20)

# Step 4: Get metrics
metrics = harness.compute_metrics()
print(f"Pass rate: {metrics.pass_rate*100:.1f}%")
print(f"Faithfulness: {metrics.faithfulness:.3f}")
print(f"Hallucination rate: {metrics.hallucination_rate:.3f}")

# Step 5: Check for regressions
regressions, summary = harness.detect_regressions()
if summary["should_block_deploy"]:
    print("❌ Deploy blocked due to regressions")
else:
    print("✅ Safe to deploy")

# Step 6: Save results
harness.save_results()

# Step 7: Print report
print(harness.generate_report())
```

## Pre-Deployment Checks (1 min)

```python
from ragstack.eval.pre_deploy_check import PreDeployChecker

# Configure checker
checker = PreDeployChecker(
    min_pass_rate=0.95,
    min_deepeval_score=0.75,
    min_ragas_score=0.75,
)

# Run checks
def my_executor(q: str, c: str) -> str:
    # Your RAG pipeline
    pass

passed, message = checker.run_checks(my_executor, skip_slow=True)

if passed:
    print("✅ Safe to deploy")
    exit(0)
else:
    print(f"❌ {message}")
    exit(1)
```

## Pytest Integration

```python
# tests/test_eval.py
from ragstack.eval.pytest_plugin import run_golden_test, run_all_golden_tests

def test_specific_case(rag_executor):
    """Test a specific golden case."""
    result = run_golden_test("fac_001", rag_executor)
    assert result.passed, f"Test failed: {result.error}"

def test_all_factual_cases(rag_executor):
    """Test all factual accuracy cases."""
    results = run_all_golden_tests(
        rag_executor, 
        category="factual"
    )
    pass_rate = sum(1 for r in results if r.passed) / len(results)
    assert pass_rate >= 0.90
```

Run with pytest:
```bash
pytest tests/test_eval.py -v
pytest tests/test_eval.py -m eval  # Only eval tests
pytest tests/test_eval.py --eval-skip-slow
```

## CI/CD Integration (GitHub Actions)

```yaml
# .github/workflows/eval.yml
name: Evaluation Suite

on: [pull_request, push]

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - run: pip install -e ".[eval]"
      
      - run: eval run --skip-slow
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      
      - uses: actions/upload-artifact@v3
        if: always()
        with:
          name: eval-results
          path: eval_results/
```

See [CI_CD_INTEGRATION.md](src/ragstack/eval/CI_CD_INTEGRATION.md) for GitLab, Jenkins, Azure Pipelines, etc.

## Understanding the Report

```
╔════════════════════════════════════════════════════════════════╗
║           AUTOMATED EVALUATION HARNESS REPORT                  ║
╚════════════════════════════════════════════════════════════════╝

Test Results: 95/100 passed (95.0%)
├─ Tests passed: 95
├─ Tests failed: 5
└─ Pass rate: 95%

📊 QUALITY METRICS
├─ DeepEval Score: 0.823 (aggregate across all DeepEval metrics)
├─ RAGAS Score: 0.787 (aggregate across all RAGAS metrics)
├─ Answer Relevance: 0.845 (how relevant is the answer to the question?)
├─ Faithfulness: 0.812 (is the answer grounded in the context?)
├─ Hallucination Rate: 0.188 (lower is better - rate of made-up facts)
└─ Context Precision: 0.756 (is retrieved context relevant?)

🔍 REGRESSION DETECTION
├─ ✅ SAFE TO DEPLOY (or ❌ REGRESSION DETECTED)
├─ Regressions: 0 (metrics that dropped > 5%)
├─ Improvements: 2 (metrics that improved > 5%)
└─ Stable: 4 (metrics within 5% of baseline)

📈 METRIC TRENDS
├─ 📈 answer_relevance: 0.845 (+2.1%) [improving]
├─ → faithfulness: 0.812 (+0.3%) [stable]
├─ 📉 hallucination_rate: 0.188 (-0.3%) [declining]
└─ ... (other metrics)
```

## Key Metrics Explained

| Metric | Range | What It Means | Ideal |
|--------|-------|--------------|-------|
| **Answer Relevance** | 0-1 | Is answer relevant to question? | > 0.80 |
| **Faithfulness** | 0-1 | Is answer grounded in context? | > 0.80 |
| **Hallucination Rate** | 0-1 | Rate of made-up facts | < 0.20 |
| **Context Precision** | 0-1 | Is retrieved context relevant? | > 0.75 |
| **Pass Rate** | 0-1 | Percentage of tests passing | > 0.95 |
| **DeepEval Score** | 0-1 | Aggregate LLM output quality | > 0.75 |
| **RAGAS Score** | 0-1 | Aggregate RAG pipeline quality | > 0.75 |

## Configuration Options

### Harness Configuration

```python
EvalHarness(
    rag_executor=executor,                    # Your RAG function
    results_dir=Path("eval_results"),         # Where to save results
    regression_threshold=5.0,                 # % change to detect regression
    deepeval_threshold=0.7,                   # Min DeepEval score
    ragas_threshold=0.7,                      # Min RAGAS score
)
```

### CLI Options

```bash
eval run \
    --skip-slow              # Skip slow/hard tests
    --max-tests 20           # Limit test count
    --category factual       # Run specific category
    --results-dir ./results  # Custom results directory
    --block-regressions      # Exit with error on regression
```

### Environment Variables

```bash
# API Keys
export ANTHROPIC_API_KEY="sk-ant-..."
export LANGSMITH_API_KEY="..."

# Evaluation settings
export EVAL_MODEL="claude-3-5-sonnet-20241022"
export EVAL_TIMEOUT="30"  # Seconds
export EVAL_LOG_LEVEL="INFO"
```

## Troubleshooting

### Q: Evaluation is too slow
**A**: Use `eval run --skip-slow` or `--max-tests 20`

### Q: Different results each run
**A**: LLM evals are non-deterministic. Use LangSmith trace replay for consistency.

### Q: API key errors
**A**: Set `ANTHROPIC_API_KEY` and `LANGSMITH_API_KEY` environment variables

### Q: DeepEval/RAGAS not found
**A**: Run `pip install -e ".[eval]"` to install all dependencies

### Q: Tests failing unexpectedly
**A**: Check logs in `eval_results/` for detailed error messages

### Q: OutOfMemory error
**A**: Use `--skip-slow` and reduce `--max-tests`

## Next Steps

1. **Integrate with your RAG pipeline**
   - Implement `rag_executor` function
   - Test with a few golden cases
   - Monitor quality metrics

2. **Add to CI/CD**
   - Copy GitHub Actions workflow
   - Or see CI_CD_INTEGRATION.md for other platforms
   - Set regression threshold for your needs

3. **Monitor trends**
   - Run evaluations regularly
   - Track improvements over time
   - Alert on regressions

4. **Custom test cases**
   - Add domain-specific golden cases
   - Target weak areas
   - Build comprehensive test suite

## Example Files

- `src/ragstack/eval/example_usage.py` - Complete examples
- `src/ragstack/eval/README.md` - Full documentation
- `src/ragstack/eval/CI_CD_INTEGRATION.md` - CI/CD setup

## API Reference

Quick reference for common operations:

```python
# Initialize
harness = EvalHarness(executor, results_dir="eval_results")

# Run tests
harness.run_all_tests(skip_slow=True, max_tests=50)
harness.run_test(single_test_case)

# Get metrics
metrics = harness.compute_metrics()
regressions, summary = harness.detect_regressions()

# Export
harness.save_results()
report = harness.generate_report()

# Pytest
run_golden_test("test_id", executor)
run_all_golden_tests(executor, category="factual")

# Pre-deploy
from ragstack.eval.pre_deploy_check import PreDeployChecker
checker = PreDeployChecker(min_pass_rate=0.95)
passed, message = checker.run_checks(executor)

# Trends
from ragstack.eval.regression_detector import RegressionDetector
detector = RegressionDetector(Path("metric_history.json"))
detector.get_trend_report()
```

## Support

- 📖 **Documentation**: `src/ragstack/eval/README.md`
- 🔧 **Examples**: `src/ragstack/eval/example_usage.py`
- 🚀 **CI/CD**: `src/ragstack/eval/CI_CD_INTEGRATION.md`
- 🐛 **Issues**: Check GitHub issues for known problems

## Key Features Summary

| Feature | Status | Details |
|---------|--------|---------|
| Golden Test Cases | ✅ | 100+ curated test cases |
| DeepEval Integration | ✅ | Answer relevance, faithfulness, coherence |
| RAGAS Integration | ✅ | Context precision/recall, faithfulness |
| LangSmith Tracing | ✅ | Execution traces and token tracking |
| Regression Detection | ✅ | Automatic regression blocking |
| Quality Trends | ✅ | Historical metric tracking |
| CLI Interface | ✅ | `eval run`, `eval show-trend`, etc. |
| Pytest Integration | ✅ | Run as pytest tests |
| Pre-Deploy Checks | ✅ | Configurable quality gates |
| CI/CD Ready | ✅ | GitHub, GitLab, Jenkins, Azure, etc. |
| HTML Reports | ✅ | Rich report generation |
| JSON Export | ✅ | Machine-readable results |

---

**Ready to evaluate?**
```bash
eval run --skip-slow
```

See detailed results in `eval_results/report_*.txt`
