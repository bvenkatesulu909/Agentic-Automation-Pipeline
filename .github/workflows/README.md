# GitHub Actions Workflows

This directory contains all GitHub Actions workflows for the ADK Agents CI/CD pipeline.

## Workflows Overview

### 1. `ci.yml` - Continuous Integration

**Trigger:** Push to `main`/`develop`, Pull Requests

**Jobs:**
- `test`: Runs unit tests, code quality checks, and security scans
- `build-and-push`: Builds Docker image and pushes to Artifact Registry
- `quality-gate`: Ensures tests and build passed before marking as deployable

**Artifacts:**
- Test coverage reports (codecov)
- Docker image (tagged with commit SHA and `latest`)

**Duration:** ~15-20 minutes

### 2. `deploy.yml` - Deployment to GKE via ArgoCD

**Trigger:** 
- Push to `main` or `develop` (automatic)
- Manual workflow dispatch with environment selection
- After successful CI completion

**Jobs:**
- `deploy`: Syncs ArgoCD applications for the target environment
- `canary-analysis`: Analyzes metrics for production deployments only
- `rollback-on-failure`: Automatic rollback if quality gates fail

**Environments:**
- `develop` → `adk-agents-staging`
- `main` → `adk-agents-production` (with canary)

**Duration:** ~30 minutes (including canary analysis wait)

### 3. `security.yml` - Security Scanning

**Trigger:** Push, Pull Requests, Daily at 2 AM

**Checks:**
- Dependency vulnerability scanning (DependencyCheck)
- Container image scanning (Trivy)
- SAST analysis (Bandit)
- Secret detection (GitGuardian)

**Reports:** SARIF format (GitHub Security tab)

**Duration:** ~20-30 minutes

### 4. `integration-tests.yml` - Integration Testing

**Trigger:** Push to `main`/`develop`, Pull Requests, Every 6 hours

**Services:**
- PostgreSQL 15
- Redis 7

**Jobs:**
- `integration-tests`: Full integration test suite with real databases
- `e2e-tests`: End-to-end tests (main branch only)

**Duration:** ~45 minutes

## Workflow Status Badges

Add these to your README.md:

```markdown
![CI Status](https://github.com/your-org/your-repo/actions/workflows/ci.yml/badge.svg)
![Deploy Status](https://github.com/your-org/your-repo/actions/workflows/deploy.yml/badge.svg)
![Security Status](https://github.com/your-org/your-repo/actions/workflows/security.yml/badge.svg)
```

## Debugging Workflows

### View Logs

1. Go to **Actions** tab in GitHub
2. Click on the workflow run
3. Click on the job to see detailed logs
4. Use search (Ctrl+F) to find errors

### Re-run Workflows

```bash
# Re-run all jobs
gh run rerun <run-id> -R your-org/your-repo

# Re-run failed jobs only
gh run rerun <run-id> --failed -R your-org/your-repo
```

### Test Locally

```bash
# Install act to run workflows locally
brew install act

# Run specific workflow
act -j test

# Run with secrets (create .secrets file)
act -j test --secret-files .secrets
```

## Environment Variables

### Available in All Workflows
- `GITHUB_SHA`: Commit SHA
- `GITHUB_REF`: Branch name
- `GITHUB_ACTOR`: User who triggered workflow
- `GITHUB_REPOSITORY`: Repository name

### Set in Workflows
- `REGISTRY`: Docker registry (us-west1-docker.pkg.dev)
- `GCP_PROJECT_ID`: GCP project ID
- `IMAGE_NAME`: Docker image name

## Secrets Required

Configure these in GitHub Settings → Secrets and variables → Actions:

| Secret | Description |
|--------|-------------|
| `WIF_PROVIDER` | Workload Identity Provider resource name |
| `WIF_SERVICE_ACCOUNT` | Service account for GCP authentication |
| `ARGOCD_SERVER` | ArgoCD server URL |
| `ARGOCD_AUTH_TOKEN` | ArgoCD API token |
| `GITGUARDIAN_API_KEY` | GitGuardian API key (optional) |

## Performance Tips

1. **Caching**: Python dependencies are cached to speed up installations
2. **Parallel Jobs**: Some jobs run in parallel (e.g., all security scans)
3. **Selective Builds**: Use `paths` to only trigger on relevant changes
4. **Matrix Builds**: Extend workflows to test on multiple Python versions

Example:
```yaml
strategy:
  matrix:
    python-version: ['3.11', '3.12']
```

## Monitoring Workflow Performance

```bash
# List workflow runs
gh run list -R your-org/your-repo

# View specific run details
gh run view <run-id> -R your-org/your-repo

# Watch live
gh run watch <run-id> -R your-org/your-repo
```

## Troubleshooting Common Issues

### Authentication Failed
- Verify WIF provider is configured correctly
- Check service account has necessary IAM roles
- Re-authenticate: `gcloud auth application-default login`

### Docker Build Timeout
- Increase `timeout-minutes` in workflow
- Check Docker build cache is working
- Optimize Dockerfile (remove unnecessary layers)

### Tests Fail Intermittently
- Check for race conditions in tests
- Increase test timeout
- Use `pytest-xdist` for parallel test execution

### Metrics Query Fails
- Ensure Prometheus is running and accessible
- Check metrics are being scraped
- Verify scrape interval (usually 30s)

## Extending Workflows

### Add a New Job

```yaml
new-job:
  runs-on: ubuntu-latest
  needs: test  # Wait for test job
  
  steps:
    - uses: actions/checkout@v4
    - name: Do something
      run: echo "Hello from new job"
```

### Add a New Trigger

```yaml
on:
  pull_request:
    paths:
      - 'src/special-module/**'  # Only trigger on changes to this path
      
  schedule:
    - cron: '0 3 * * *'  # Run daily at 3 AM
```

### Use Matrix for Multiple Versions

```yaml
strategy:
  matrix:
    python-version: ['3.11', '3.12']
    os: [ubuntu-latest, macos-latest]
    
steps:
  - uses: actions/setup-python@v4
    with:
      python-version: ${{ matrix.python-version }}
```

## Cost Optimization

- Free tier includes: 2,000 minutes/month on Ubuntu
- Windows/macOS runners are 3x-10x more expensive
- Stick to Ubuntu runners unless needed
- Use caching to reduce build times
- Consider GitHub-hosted runners vs self-hosted for large repos

## References

- [GitHub Actions Documentation](https://docs.github.com/actions)
- [Google Cloud Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [ArgoCD Webhook Integration](https://argo-cd.readthedocs.io/en/stable/operator-manual/webhook/)
