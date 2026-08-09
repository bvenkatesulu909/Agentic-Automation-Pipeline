# CI/CD Quick Start Guide

Get your CI/CD pipeline running in 5 steps.

## Step 1: Set Up GitHub Secrets (5 minutes)

Go to **GitHub Settings → Secrets and variables → Actions** and add:

```
WIF_PROVIDER = projects/YOUR_PROJECT/locations/global/workloadIdentityPools/github-actions/providers/github
WIF_SERVICE_ACCOUNT = github-actions@YOUR_PROJECT.iam.gserviceaccount.com
ARGOCD_SERVER = argocd.YOUR_DOMAIN.com
ARGOCD_AUTH_TOKEN = <get from: argocd account generate-token --account cicd-user>
```

**Script to generate WIF values:**
```bash
gcloud iam workload-identity-pools describe github-actions --location=global --format='value(name)'
gcloud iam workload-identity-pools providers describe github --location=global --workload-identity-pool=github-actions --format='value(name)'
```

## Step 2: Install ArgoCD (10 minutes)

```bash
# 1. Create namespace
kubectl create namespace argocd

# 2. Install ArgoCD
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# 3. Wait for it to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=argocd-server \
  -n argocd --timeout=300s

# 4. Get admin password
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d

# 5. Port forward to access
kubectl port-forward -n argocd svc/argocd-server 8080:443
# Visit: https://localhost:8080

# 6. Generate token for CI/CD
argocd account generate-token --account cicd-user
# Copy token to GitHub secrets as ARGOCD_AUTH_TOKEN
```

## Step 3: Deploy ArgoCD Applications (5 minutes)

```bash
# Apply ArgoCD namespace and applications
kubectl apply -f k8s/argocd/namespace.yaml
kubectl apply -f k8s/argocd/apps/adk-agents-staging.yaml
kubectl apply -f k8s/argocd/apps/adk-agents-production.yaml

# Verify
argocd app get adk-agents-staging
argocd app get adk-agents-production
```

## Step 4: Install Monitoring (Flagger + Prometheus) (10 minutes)

**For Production Cluster Only:**

```bash
# 1. Install Prometheus Operator
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace

# 2. Install Flagger for canary deployments
helm repo add flagger https://flagger.app
helm repo update
helm install flagger flagger/flagger \
  --namespace flagger-system \
  --create-namespace

# 3. Install LoadTester for synthetic traffic
helm install flagger-loadtester flagger/loadtester \
  --namespace flagger-system

# 4. Apply Prometheus rules
kubectl apply -f k8s/monitoring/prometheus-rules.yaml

# 5. Verify
kubectl get pods -n monitoring
kubectl get pods -n flagger-system
```

## Step 5: Test the Pipeline (5 minutes)

```bash
# 1. Make a small change
echo "# Updated" >> README.md
git add README.md
git commit -m "test: trigger CI pipeline"
git push origin develop

# 2. Watch GitHub Actions
# Go to: https://github.com/YOUR_ORG/YOUR_REPO/actions
# Click on the latest workflow run

# 3. Watch deployment
argocd app wait adk-agents-staging --sync
kubectl get pods -n adk-agents -w

# 4. Verify app is running
kubectl port-forward svc/adk-agents -n adk-agents 8000:8000
curl http://localhost:8000/health
```

## Key Commands Reference

```bash
# Check GitHub Actions
gh run list -R your-org/your-repo
gh run view <run-id> -R your-org/your-repo

# Check ArgoCD
argocd app list
argocd app get adk-agents-production
argocd app sync adk-agents-production

# Check deployment
kubectl get deployment adk-agents -n adk-agents
kubectl logs -n adk-agents -l app=adk-agents --tail=50
kubectl top pods -n adk-agents

# Check canary (production only)
kubectl get canary -n adk-agents
kubectl describe canary adk-agents -n adk-agents

# Check metrics
kubectl port-forward -n monitoring svc/prometheus 9090:9090
# Visit: http://localhost:9090
```

## Common Workflows

### Deploy to Staging
```bash
git checkout develop
git pull origin develop
# Make changes
git commit -m "feature: add new feature"
git push origin develop
# GitHub Actions automatically deploys to staging
```

### Deploy to Production (with canary)
```bash
git checkout main
git pull origin main
# Create feature branch
git checkout -b release/v1.2.0
# Make changes
git commit -m "release: v1.2.0"
git push origin release/v1.2.0
# Create pull request
# After review, merge to main
# Automatic canary deployment starts
```

### Monitor Production Deployment
```bash
# Watch canary progression
kubectl get canary -n adk-agents -w

# Check metrics
kubectl exec -n monitoring prometheus-0 -- \
  promtool query instant 'adk_agents:request_error_rate_5m'

# Manual promote if needed
argocd app set adk-agents-production -p adk-agents.canaryWeight=100
```

### Rollback (if needed)
```bash
# Automatic (triggered by quality gates)
# If manual rollback needed:
kubectl rollout undo deployment/adk-agents -n adk-agents

# Verify
kubectl rollout status deployment/adk-agents -n adk-agents
```

## Troubleshooting

### Workflow stuck on `deploy` step
```bash
# Check ArgoCD connection
argocd app get adk-agents-staging

# Manually sync if needed
argocd app sync adk-agents-staging --force

# Check logs
kubectl logs -n argocd deployment/argocd-application-controller
```

### Metrics not available for canary
```bash
# Check Prometheus is scraping metrics
kubectl port-forward -n monitoring svc/prometheus 9090:9090
# Visit: http://localhost:9090/targets

# Check ServiceMonitor is created
kubectl get servicemonitor -n adk-agents
kubectl describe servicemonitor adk-agents -n adk-agents
```

### Pods not reaching ready state
```bash
# Check pod logs
kubectl logs -n adk-agents <pod-name> --tail=100

# Check events
kubectl describe pod -n adk-agents <pod-name>

# Check resource constraints
kubectl top pods -n adk-agents
kubectl get events -n adk-agents --sort-by='.lastTimestamp'
```

## Next Steps

1. ✅ Configure GitHub secrets
2. ✅ Install ArgoCD
3. ✅ Deploy applications
4. ✅ Install monitoring
5. **Read full documentation:** [CI_CD_SETUP.md](./CI_CD_SETUP.md)
6. **Use deployment checklist:** [DEPLOYMENT_CHECKLIST.md](./DEPLOYMENT_CHECKLIST.md)
7. **Customize for your needs** (quality gates, alert channels, etc.)

## Dashboard URLs

| Service | URL | Default Credentials |
|---------|-----|-------------------|
| ArgoCD | https://localhost:8080 | admin / [see Step 2] |
| Prometheus | http://localhost:9090 | N/A |
| Grafana | http://localhost:3000 | admin / prom-operator |

## Support

- **Docs**: See [CI_CD_SETUP.md](./CI_CD_SETUP.md) for detailed setup
- **Issues**: Check [Troubleshooting Guide](./CI_CD_SETUP.md#troubleshooting)
- **Workflows**: See [.github/workflows/README.md](./.github/workflows/README.md)

---

**Done!** Your CI/CD pipeline is now ready. Push a change to test it out.
