# Deployment Checklist

Use this checklist to verify readiness before deploying to production.

## Pre-Deployment (Before Push to Main)

### Code Quality
- [ ] All unit tests pass locally: `pytest tests/`
- [ ] Code coverage meets minimum threshold (>80%)
- [ ] Linting passes: `ruff check src/`
- [ ] Type checking passes (if using mypy)
- [ ] Security scan shows no critical issues: `bandit -r src/`

### Documentation
- [ ] Feature documented in README.md
- [ ] API changes documented (if applicable)
- [ ] Database migrations documented (if applicable)
- [ ] Configuration changes documented

### Git
- [ ] Branch is up to date with `main`: `git rebase origin/main`
- [ ] Commit messages are clear and descriptive
- [ ] No unintended files in changeset: `git diff origin/main`
- [ ] Code review completed and approved

## Deployment Stage (GitHub Actions - Automated)

### CI Pipeline
- [ ] **CI workflow** passes:
  - [ ] Unit tests run successfully
  - [ ] Code quality checks pass
  - [ ] Security checks pass (bandit, dependency check)

### Build & Push
- [ ] **Build workflow** completes:
  - [ ] Docker image builds successfully
  - [ ] Image pushed to Artifact Registry
  - [ ] Image scanned for vulnerabilities (Trivy)

### Integration Tests
- [ ] **Integration test** workflow passes:
  - [ ] Tests with real database/Redis
  - [ ] E2E tests on main branch only

### Deployment to Staging
- [ ] **Deploy workflow** for `develop`:
  - [ ] Staging deployment syncs via ArgoCD
  - [ ] All pods reach ready state
  - [ ] Health checks pass

## Staging Validation (Manual - Before Production)

### Functionality
- [ ] Main user flows work as expected
- [ ] API endpoints respond correctly
- [ ] Database queries execute without errors
- [ ] Logging shows expected messages

### Performance
- [ ] Response times are acceptable (<2s P95)
- [ ] Memory usage is within limits (<2GB)
- [ ] CPU usage is reasonable (<80%)
- [ ] No memory leaks in extended run

### Integration
- [ ] External API calls work (if applicable)
- [ ] Database connections are stable
- [ ] Cache is working correctly (if used)
- [ ] Message queues process correctly (if used)

### Monitoring
- [ ] Prometheus metrics are being collected
- [ ] Alerts are configured and working
- [ ] Logging is captured in CloudLogging/ELK
- [ ] Traces are visible in tracing system (if enabled)

## Production Deployment (After Staging Validation)

### Pre-Deployment
- [ ] Stakeholders notified of upcoming deployment
- [ ] Rollback plan documented
- [ ] On-call engineer is aware
- [ ] Maintenance window declared (if needed)

### Deploy to Production
- [ ] **Deploy workflow** for `main`:
  - [ ] Production deployment syncs via ArgoCD
  - [ ] Canary deployment starts (10% traffic)

### Canary Phase 1 (10% traffic, 5 minutes)
- [ ] No critical errors in logs
- [ ] Error rate < 5%
- [ ] Latency P95 < 2s
- [ ] No memory leaks
- [ ] No pod restarts
- [ ] Proceed to next phase or rollback

### Canary Phase 2 (20% traffic, 5 minutes)
- [ ] Same checks as Phase 1
- [ ] No increase in error rates
- [ ] Performance metrics stable
- [ ] Proceed to Phase 3 or rollback

### Canary Phase 3 (50% traffic, 5 minutes)
- [ ] Same checks as previous phases
- [ ] Monitor user-reported issues
- [ ] Proceed to full rollout or rollback

### Full Rollout (100% traffic)
- [ ] All replicas running and healthy
- [ ] Load is evenly distributed
- [ ] Metrics look good
- [ ] No degradation compared to previous version

## Post-Deployment

### Immediate (First 30 Minutes)
- [ ] Monitor error rates (should be < 1%)
- [ ] Monitor latency (should be < 2s P95)
- [ ] Check for any alerts
- [ ] Verify no pod crashes
- [ ] Monitor memory/CPU usage
- [ ] Check application-specific metrics

### Short-term (First 4 Hours)
- [ ] User reports of issues? → None expected
- [ ] Performance stable?
- [ ] All health checks passing?
- [ ] Database performance good?
- [ ] No resource exhaustion?

### Long-term (First 24 Hours)
- [ ] No memory leaks (compare memory over time)
- [ ] No increasing error rates
- [ ] Performance remains consistent
- [ ] No cascading failures
- [ ] Users reporting success in new features

## Rollback Procedures

### Automatic Rollback (Triggered if)
- [ ] Error rate exceeds 5% for 5+ minutes
- [ ] P95 latency exceeds 2s for 5+ minutes
- [ ] Pod crash looping detected
- [ ] Quality gates fail in production

**What happens:**
1. Previous stable version is restored
2. Traffic returns to old version
3. Incident is logged
4. On-call engineer is notified

### Manual Rollback (if needed)

```bash
# If automatic rollback doesn't work:
kubectl rollout undo deployment/adk-agents -n adk-agents

# Monitor rollback
kubectl rollout status deployment/adk-agents -n adk-agents

# Verify services are stable
kubectl get pods -n adk-agents
```

## Post-Incident (if Rollback Occurred)

- [ ] Root cause analysis completed
- [ ] Issue documented with reproduction steps
- [ ] Fix implemented and tested in staging
- [ ] Additional tests added to prevent recurrence
- [ ] Runbook updated if needed
- [ ] Team debriefing scheduled

## Environment-Specific Notes

### Staging Environment
- Low traffic, one replica
- Used for testing new features
- Can have more experimental rollouts
- Reset daily or on-demand

### Production Environment
- High traffic, 3 replicas minimum
- Canary deployments enabled
- Strict quality gates enforced
- Auto-rollback on failure
- Health checks every 10 seconds

## Quick Reference Commands

```bash
# Check deployment status
kubectl get deployment adk-agents -n adk-agents

# View recent logs
kubectl logs -n adk-agents -l app=adk-agents --tail=50

# Check resource usage
kubectl top pods -n adk-agents

# Describe pod for errors
kubectl describe pod -n adk-agents <pod-name>

# Port forward to test locally
kubectl port-forward svc/adk-agents -n adk-agents 8000:8000

# Force sync ArgoCD
argocd app sync adk-agents-production --force

# View ArgoCD app status
argocd app get adk-agents-production

# Check canary status
kubectl get canary -n adk-agents

# Rollback to previous version
kubectl rollout undo deployment/adk-agents -n adk-agents
```

## Contact & Escalation

- **On-Call Engineer**: [Contact method]
- **Team Lead**: [Contact method]
- **Incident Commander**: [Contact method]

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-09 | Platform Team | Initial checklist |
