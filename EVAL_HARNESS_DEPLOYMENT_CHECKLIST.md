# Evaluation Harness Deployment Checklist

Complete checklist for deploying the Automated Evaluation Harness in production.

## Pre-Deployment Setup (Complete Before First Deploy)

- [ ] **Install evaluation dependencies**
  ```bash
  pip install -e ".[eval]"
  ```
  Verify: `eval count-cases` should output 100+

- [ ] **Configure API keys**
  ```bash
  export ANTHROPIC_API_KEY="sk-ant-..."
  export LANGSMITH_API_KEY="..."
  ```
  Verify: Can run `eval run --skip-slow` without errors

- [ ] **Run baseline evaluation**
  ```bash
  eval run --skip-slow
  ```
  - Expected time: 5-10 minutes
  - Expected pass rate: > 80%
  - Save results as baseline

- [ ] **Review initial report**
  ```bash
  cat eval_results/report_*.txt
  ```
  Look for:
  - ✅ Reasonable metric scores (> 0.7 for main metrics)
  - ✅ No unexpected failures
  - ✅ Clear trend data

- [ ] **Set regression thresholds**
  Review metrics from baseline:
  ```python
  # In your deploy script
  EvalHarness(
      rag_executor=executor,
      regression_threshold=5.0,      # Adjust based on variance
      deepeval_threshold=0.75,       # Your acceptable minimum
      ragas_threshold=0.75,          # Your acceptable minimum
  )
  ```

- [ ] **Configure pre-deploy checks**
  ```python
  checker = PreDeployChecker(
      min_pass_rate=0.95,            # Target pass rate
      min_deepeval_score=0.75,       # Minimum acceptable
      min_ragas_score=0.75,          # Minimum acceptable
      regression_threshold=5.0,      # % regression tolerance
  )
  ```

## CI/CD Integration (Choose Your Platform)

### GitHub Actions

- [ ] Create `.github/workflows/eval.yml`
  ```yaml
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
          with:
            name: eval-results
            path: eval_results/
  ```

- [ ] Add repository secrets
  - `ANTHROPIC_API_KEY`
  - `LANGSMITH_API_KEY` (optional)

- [ ] Test workflow
  - Create dummy PR
  - Verify workflow runs successfully
  - Check artifact upload

- [ ] Configure branch protection
  - Require evaluation workflow to pass
  - Set minimum pass rate in branch rules

### GitLab CI

- [ ] Create `.gitlab-ci.yml` eval job
- [ ] Add protected variables for API keys
- [ ] Test on merge request
- [ ] Configure merge request approval

### Jenkins

- [ ] Create Jenkinsfile with eval stage
- [ ] Configure credentials for API keys
- [ ] Set up artifact archiving
- [ ] Configure email notifications on failure

### Other Platforms

- [ ] See `src/ragstack/eval/CI_CD_INTEGRATION.md` for examples
- [ ] Copy appropriate workflow template
- [ ] Configure API key secrets
- [ ] Test end-to-end

## Regression Detection Setup

- [ ] **Initialize metric history**
  ```bash
  eval run --skip-slow
  ```
  This creates `eval_results/metric_history.json`

- [ ] **Verify regression detection**
  ```bash
  # Simulate a metric drop to test
  eval show-trend
  ```
  Should show "improving", "stable", or "declining" trends

- [ ] **Configure regression thresholds**
  - Default: 5% drop = regression
  - For strict QA: 2-3%
  - For rapid iteration: 8-10%

- [ ] **Test regression blocking**
  - Modify evaluator to return lower scores
  - Confirm deployment is blocked
  - Restore and verify unblocking

## Monitoring & Alerting

- [ ] **Set up LangSmith project**
  ```bash
  export LANGSMITH_API_KEY="..."
  export LANGCHAIN_PROJECT="ragstack-eval"
  ```
  - Visit https://smith.langchain.com
  - Create project "ragstack-eval"
  - Copy API key to secrets

- [ ] **Configure email notifications**
  GitHub Actions:
  ```yaml
  - name: Send failure email
    if: failure()
    uses: dawidd6/action-send-mail@v3
    with:
      server_address: ${{ secrets.EMAIL_SERVER }}
      server_port: ${{ secrets.EMAIL_PORT }}
      username: ${{ secrets.EMAIL_USERNAME }}
      password: ${{ secrets.EMAIL_PASSWORD }}
      subject: "Evaluation Failed"
      to: "team@example.com"
  ```

- [ ] **Configure Slack notifications**
  ```bash
  # Add Slack webhook to repository secrets
  SLACK_WEBHOOK_URL="https://hooks.slack.com/..."
  ```

- [ ] **Set up metric dashboard**
  - Export metrics to monitoring system (Prometheus, CloudWatch, etc.)
  - Create dashboard showing:
    - Pass rate trend
    - Key metric scores
    - Regression count
    - Test execution time

## Deployment Process

### Before Each Deploy

1. [ ] **Run local evaluation**
   ```bash
   eval run --skip-slow
   ```
   - Confirm > 95% pass rate
   - Review any regressions
   - Check metric scores above thresholds

2. [ ] **Run pre-deploy checks**
   ```python
   from ragstack.eval.pre_deploy_check import main
   exit_code = main()
   if exit_code != 0:
       sys.exit("Deploy blocked by evaluation checks")
   ```

3. [ ] **Review trend report**
   ```bash
   eval show-trend
   ```
   - Confirm improving or stable trends
   - No unexpected degradation

4. [ ] **Commit results** (optional)
   ```bash
   git add eval_results/metric_history.json
   git commit -m "Update metric history"
   ```

5. [ ] **Create deployment PR**
   - Include evaluation report in PR description
   - Link to CI/CD results
   - Summarize metric changes

### Deployment Checklist

- [ ] **Pre-flight checks**
  - [ ] All tests passing
  - [ ] No regressions detected
  - [ ] Key metrics above threshold
  - [ ] Evaluation report reviewed

- [ ] **Deploy**
  ```bash
  # Your deployment command
  ./deploy.sh --environment production
  ```

- [ ] **Monitor in production**
  - [ ] LangSmith traces show normal activity
  - [ ] No increase in errors
  - [ ] Latency within expected range

- [ ] **Post-deploy validation**
  - [ ] Run quick smoke tests
  - [ ] Verify key functionality works
  - [ ] Check monitoring dashboards

## Ongoing Maintenance

### Daily/Weekly

- [ ] Monitor evaluation metrics
  - Check if any metrics dropping
  - Alert if any regressions
  - Review new test failures

- [ ] Review LangSmith traces
  - Any unusual patterns?
  - Token usage as expected?
  - Latency within SLA?

### Monthly

- [ ] Full evaluation suite run
  ```bash
  eval run  # Run all 100+ tests
  ```

- [ ] Review trend report
  - Long-term metric changes
  - Identify areas for improvement
  - Adjust thresholds if needed

- [ ] Update golden test cases
  - Add new edge cases found
  - Remove obsolete tests
  - Improve difficult tests

### Quarterly

- [ ] Comprehensive audit
  - Review all 100+ test results
  - Identify weak areas
  - Plan improvements

- [ ] Update baselines
  - Commit current metrics as new baseline
  - Reset history if major refactor
  - Document changes

- [ ] Review thresholds
  - Are regression thresholds appropriate?
  - Should we tighten/loosen requirements?
  - Update based on business needs

## Troubleshooting During Deployment

### Scenario: Evaluation Fails to Run

**Symptoms**: Error running `eval run`

**Solutions**:
```bash
# 1. Check dependencies
pip install -e ".[eval]"

# 2. Check API keys
echo $ANTHROPIC_API_KEY
echo $LANGSMITH_API_KEY

# 3. Run with verbose logging
eval run --skip-slow -v

# 4. Check logs
tail -f eval_results/*.log
```

### Scenario: Regression Detected

**Symptoms**: ❌ REGRESSION DETECTED in report

**Investigation**:
```bash
# 1. Show trend
eval show-trend

# 2. Compare current metrics to baseline
cat eval_results/metric_history.json | jq .

# 3. Run failing tests in isolation
eval run --category factual  # If specific category fails

# 4. Check recent code changes
git diff HEAD~5
```

**Resolution**:
1. Identify cause (code change, data change, model change)
2. Fix the issue
3. Re-run evaluation
4. Update baseline if intentional improvement

### Scenario: Tests Timing Out

**Symptoms**: Tests running very slowly or timing out

**Solutions**:
```bash
# Use faster configuration
eval run --skip-slow --max-tests 20

# Increase timeout in CI/CD (GitHub Actions example)
timeout-minutes: 60  # Increase from 45

# Check for resource issues
top  # Monitor CPU/memory
```

### Scenario: Inconsistent Results

**Symptoms**: Different results on different runs

**Causes**:
- LLM sampling (different outputs each run)
- Different API version deployed
- Different model version

**Solutions**:
- Use LangSmith trace replay for reproducibility
- Fix temperature/seed for evaluations
- Monitor for model version changes

## Rollback Procedure

If deployment causes significant regression:

1. [ ] **Identify the issue**
   ```bash
   eval show-trend
   cat eval_results/report_*.txt
   ```

2. [ ] **Decide to rollback**
   - If key metric dropped > 10%: Rollback
   - If pass rate < 80%: Rollback
   - Otherwise: Investigate and fix forward

3. [ ] **Execute rollback**
   ```bash
   git revert <commit-hash>
   ./deploy.sh --environment production
   ```

4. [ ] **Post-rollback validation**
   ```bash
   eval run --skip-slow
   ```
   Confirm metrics return to previous state

5. [ ] **Root cause analysis**
   - What changed?
   - Why did it fail QA?
   - How to prevent in future?

## Success Criteria

Your deployment is successful when:

✅ **Pre-Deploy Checks**
- [ ] Pass rate ≥ 95%
- [ ] No regressions detected
- [ ] All key metrics > threshold
- [ ] Report generated successfully

✅ **Post-Deploy Validation**
- [ ] Application runs without errors
- [ ] LangSmith traces normal
- [ ] Response times acceptable
- [ ] No alerts triggered

✅ **Ongoing Monitoring**
- [ ] Metrics stable over time
- [ ] No unexpected degradation
- [ ] Trends improving/stable

## Quick Reference Commands

```bash
# Count test cases
eval count-cases

# Export test cases
eval export-cases --output cases.json

# Run specific category
eval run --category factual

# Run with time limit
eval run --skip-slow --max-tests 50

# Show trends
eval show-trend

# Run pre-deploy checks
python -c "from ragstack.eval.pre_deploy_check import main; exit(main())"
```

## Support & Resources

- 📖 Full docs: `src/ragstack/eval/README.md`
- 🚀 Quick start: `EVAL_HARNESS_QUICKSTART.md`
- 🔧 Examples: `src/ragstack/eval/example_usage.py`
- 🌍 CI/CD: `src/ragstack/eval/CI_CD_INTEGRATION.md`

## Sign-Off

- [ ] I understand the evaluation harness
- [ ] I have tested locally
- [ ] CI/CD pipeline is configured
- [ ] Monitoring is set up
- [ ] Team is trained
- [ ] Runbooks are documented
- [ ] Ready for production deployment

**Deployment Approved By**: _________________  
**Date**: _________________  
**Notes**: _________________

---

**Need help?** Check the documentation or run `eval run --help`
