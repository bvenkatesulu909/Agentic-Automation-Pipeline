# Setup Execution Checklist

Complete this checklist to set up your CI/CD pipeline. Estimated time: 1-2 hours.

## Phase 1: Prerequisites (15 minutes)

### 1.1 Verify GCP Access
- [ ] Can access GCP project: `gcloud projects list`
- [ ] Authenticated with GCP: `gcloud auth login`
- [ ] Have `kubectl` installed: `kubectl version --client`
- [ ] Have GKE clusters:
  - [ ] `adk-staging-cluster` in `us-west1`
  - [ ] `adk-prod-cluster` in `us-west1` (if production ready)

### 1.2 Verify GitHub Access
- [ ] Have write access to repository
- [ ] Can create secrets: Settings → Secrets and variables → Actions
- [ ] Repository is public (for Actions to work with private runners)

### 1.3 Verify Docker Setup
- [ ] Docker installed locally: `docker version`
- [ ] Can access Artifact Registry: `gcloud auth configure-docker us-west1-docker.pkg.dev`

## Phase 2: GCP Workload Identity Setup (30 minutes)

### 2.1 Create Service Account

```bash
# Run these commands
gcloud iam service-accounts create github-actions \
  --display-name="GitHub Actions CI/CD" \
  --project=venkatesh-68cb677e

# Grant necessary roles
gcloud projects add-iam-policy-binding venkatesh-68cb677e \
  --member="serviceAccount:github-actions@venkatesh-68cb677e.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding venkatesh-68cb677e \
  --member="serviceAccount:github-actions@venkatesh-68cb677e.iam.gserviceaccount.com" \
  --role="roles/container.developer"

gcloud projects add-iam-policy-binding venkatesh-68cb677e \
  --member="serviceAccount:github-actions@venkatesh-68cb677e.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
```

- [ ] Service account created
- [ ] Roles assigned successfully

### 2.2 Create Workload Identity Pool

```bash
# Create pool
gcloud iam workload-identity-pools create "github-actions" \
  --location=global \
  --display-name="GitHub Actions" \
  --project=venkatesh-68cb677e

# Save the pool name
POOL_NAME=$(gcloud iam workload-identity-pools describe "github-actions" \
  --location=global \
  --format='value(name)' \
  --project=venkatesh-68cb677e)

echo "Pool Name: $POOL_NAME"
```

- [ ] Pool created successfully
- [ ] Pool name saved

### 2.3 Create OIDC Provider

```bash
# Replace YOUR-ORG/YOUR-REPO with your actual GitHub repo
export GITHUB_REPO="bvenkatesulu909/adk-agents"

gcloud iam workload-identity-pools providers create-oidc "github" \
  --location=global \
  --workload-identity-pool="github-actions" \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,assertion.aud=assertion.aud,assertion.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-condition="assertion.repository == '$GITHUB_REPO'" \
  --project=venkatesh-68cb677e
```

- [ ] OIDC provider created

### 2.4 Create Service Account Binding

```bash
export WORKLOAD_IDENTITY_POOL="projects/venkatesh-68cb677e/locations/global/workloadIdentityPools/github-actions/providers/github"
export SERVICE_ACCOUNT="github-actions@venkatesh-68cb677e.iam.gserviceaccount.com"

gcloud iam service-accounts add-iam-policy-binding $SERVICE_ACCOUNT \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/locations/global/workloadIdentityPools/github-actions/attribute.repository/$GITHUB_REPO" \
  --project=venkatesh-68cb677e
```

- [ ] Binding created

### 2.5 Save WIF Provider URI

```bash
# Get provider URI
gcloud iam workload-identity-pools providers describe "github" \
  --workload-identity-pool="github-actions" \
  --location=global \
  --format='value(name)' \
  --project=venkatesh-68cb677e
```

- [ ] Provider URI: `projects/[PROJECT]/locations/global/workloadIdentityPools/github-actions/providers/github`
- [ ] Service Account: `github-actions@venkatesh-68cb677e.iam.gserviceaccount.com`

## Phase 3: GitHub Secrets Setup (10 minutes)

### 3.1 Navigate to GitHub Settings
1. Go to: https://github.com/YOUR_ORG/YOUR_REPO/settings/secrets/actions
2. Click "New repository secret"

### 3.2 Add Secrets

Add these three secrets (one at a time):

1. **Secret Name**: `WIF_PROVIDER`
   - **Value**: `projects/venkatesh-68cb677e/locations/global/workloadIdentityPools/github-actions/providers/github`
   - [ ] Added

2. **Secret Name**: `WIF_SERVICE_ACCOUNT`
   - **Value**: `github-actions@venkatesh-68cb677e.iam.gserviceaccount.com`
   - [ ] Added

3. **Secret Name**: `ARGOCD_SERVER` (temporary, update after ArgoCD install)
   - **Value**: `argocd.example.com` (placeholder, will update)
   - [ ] Added

4. **Secret Name**: `ARGOCD_AUTH_TOKEN` (temporary, update after ArgoCD install)
   - **Value**: `temp-token` (placeholder, will update)
   - [ ] Added

**Verification**: Go back to settings, you should see all 4 secrets listed (values hidden)

## Phase 4: ArgoCD Installation (30 minutes)

### 4.1 Connect to Staging Cluster

```bash
gcloud container clusters get-credentials adk-staging-cluster \
  --region us-west1 \
  --project venkatesh-68cb677e
```

- [ ] Connected to staging cluster
- [ ] Verify: `kubectl cluster-info`

### 4.2 Create ArgoCD Namespace

```bash
kubectl create namespace argocd
```

- [ ] Namespace created
- [ ] Verify: `kubectl get namespace argocd`

### 4.3 Install ArgoCD

```bash
kubectl apply -n argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

- [ ] Installation started
- [ ] Wait for pods to be ready

### 4.4 Wait for ArgoCD to Be Ready

```bash
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/name=argocd-server \
  -n argocd \
  --timeout=300s
```

- [ ] All pods ready
- [ ] Verify: `kubectl get pods -n argocd`

### 4.5 Get Admin Password

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d; echo
```

- [ ] Password retrieved: `__________` (save this)

### 4.6 Set Up Port Forward

```bash
kubectl port-forward -n argocd svc/argocd-server 8080:443
```

- [ ] Port forward active
- [ ] Access: https://localhost:8080
- [ ] Login: admin / `[password from 4.5]`

### 4.7 Update Admin Password (Recommended)

In ArgoCD UI:
1. Login with admin/initial password
2. Click admin (top right) → Change password
3. Enter new password

- [ ] Password changed

### 4.8 Generate API Token for CI/CD

In ArgoCD UI or CLI:

```bash
argocd account generate-token --account cicd-user
```

If user doesn't exist, create first:
```bash
argocd account create cicd-user --policy role:admin
```

- [ ] Token generated: `eyJhbG...` (save this)

### 4.9 Update GitHub Secrets

Update the two ArgoCD secrets in GitHub:

1. **ARGOCD_SERVER**: `argocd.staging.example.com` (or your actual ArgoCD URL)
2. **ARGOCD_AUTH_TOKEN**: `[token from 4.8]`

- [ ] Secrets updated in GitHub

### 4.10 Create ArgoCD Namespace and Applications

```bash
# Create namespaces
kubectl apply -f k8s/argocd/namespace.yaml

# Create ArgoCD applications
kubectl apply -f k8s/argocd/apps/adk-agents-staging.yaml
# kubectl apply -f k8s/argocd/apps/adk-agents-production.yaml (skip if no prod cluster)
```

- [ ] Namespaces created
- [ ] Applications created
- [ ] Verify: `kubectl get application -n argocd`

## Phase 5: Monitoring Setup (30 minutes - OPTIONAL for staging, REQUIRED for production)

### 5.1 Install Prometheus Stack

```bash
# Add Prometheus Helm repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install Prometheus
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring \
  --create-namespace
```

- [ ] Prometheus installed
- [ ] Verify: `kubectl get pods -n monitoring`

### 5.2 Install Flagger (Production Only)

```bash
# Add Flagger Helm repo
helm repo add flagger https://flagger.app
helm repo update

# Install Flagger
helm install flagger flagger/flagger \
  --namespace flagger-system \
  --create-namespace

# Install LoadTester
helm install flagger-loadtester flagger/loadtester \
  --namespace flagger-system
```

- [ ] Flagger installed
- [ ] Verify: `kubectl get pods -n flagger-system`

### 5.3 Apply Prometheus Rules

```bash
kubectl apply -f k8s/monitoring/prometheus-rules.yaml
```

- [ ] Rules applied
- [ ] Verify: `kubectl get prometheusrule -n monitoring`

## Phase 6: Test the Pipeline (15 minutes)

### 6.1 Make a Test Commit

```bash
# Create a test branch
git checkout -b test/ci-pipeline

# Make a small change
echo "# CI/CD Pipeline Tested" >> README.md

# Commit and push
git add README.md
git commit -m "test: verify CI pipeline"
git push origin test/ci-pipeline
```

- [ ] Branch pushed

### 6.2 Create Pull Request

1. Go to GitHub repository
2. Click "Compare & pull request"
3. Create PR against `develop`

- [ ] PR created

### 6.3 Monitor GitHub Actions

1. Go to Actions tab
2. Watch the CI workflow run

- [ ] Tests passing
- [ ] Build successful
- [ ] Image pushed to registry

### 6.4 Merge Pull Request

Once CI passes:
1. Click "Squash and merge"
2. Confirm

- [ ] PR merged to develop

### 6.5 Monitor Deployment

```bash
# Watch ArgoCD sync
argocd app wait adk-agents-staging --sync

# Watch pods
kubectl get pods -n adk-agents -w
```

- [ ] Staging deployment synced
- [ ] Pods running

### 6.6 Verify Application

```bash
# Port forward to app
kubectl port-forward svc/adk-agents -n adk-agents 8000:8000

# Test health endpoint
curl http://localhost:8000/health
```

- [ ] Application responding
- [ ] Health check passes

## Phase 7: Production Setup (Optional - 30 minutes)

### 7.1 Connect to Production Cluster

```bash
gcloud container clusters get-credentials adk-prod-cluster \
  --region us-west1 \
  --project venkatesh-68cb677e
```

- [ ] Connected to production cluster

### 7.2 Repeat ArgoCD Installation (Steps 4.2-4.4)

- [ ] ArgoCD installed on production
- [ ] Token generated
- [ ] GitHub secrets updated (if using different server)

### 7.3 Deploy Production Applications

```bash
# Create namespaces
kubectl apply -f k8s/argocd/namespace.yaml

# Create production application (with canary)
kubectl apply -f k8s/argocd/apps/adk-agents-production.yaml
```

- [ ] Production app created

### 7.4 Install Monitoring Stack

```bash
# Follow Phase 5.1-5.3 steps for production cluster
```

- [ ] Monitoring installed on production

### 7.5 Test Production Deployment

```bash
# Push to main branch
git checkout main
git merge --no-ff test/ci-pipeline
git push origin main

# Monitor canary
kubectl get canary -n adk-agents -w
kubectl describe canary adk-agents -n adk-agents
```

- [ ] Canary deployment started
- [ ] All phases completing successfully
- [ ] Pods reaching ready state

## Phase 8: Post-Setup Verification (10 minutes)

### 8.1 Verify All Components

```bash
# GitHub Actions
echo "GitHub Actions: Check https://github.com/YOUR_ORG/YOUR_REPO/actions"

# ArgoCD
echo "ArgoCD Applications:"
argocd app list

# Kubernetes deployments
echo "Deployments:"
kubectl get deployment -n adk-agents

# Pods
echo "Pods:"
kubectl get pods -n adk-agents

# Services
echo "Services:"
kubectl get svc -n adk-agents
```

- [ ] All workflows shown
- [ ] Applications synced
- [ ] Deployments healthy
- [ ] All pods running

### 8.2 Configure Optional Features

- [ ] Feature flags server deployed (already in base config)
- [ ] ServiceMonitor created for Prometheus
- [ ] Network policies applied (production)

### 8.3 Set Up Notifications (Optional)

Configure alerts to send to:
- [ ] Slack (recommended)
- [ ] Email
- [ ] PagerDuty
- [ ] Custom webhook

## Phase 9: Documentation Review (10 minutes)

- [ ] Read [CICD_QUICKSTART.md](./CICD_QUICKSTART.md) for quick reference
- [ ] Read [CI_CD_SETUP.md](./CI_CD_SETUP.md) for detailed setup
- [ ] Read [DEPLOYMENT_CHECKLIST.md](./DEPLOYMENT_CHECKLIST.md) for deployment procedures
- [ ] Bookmark [.github/workflows/README.md](./.github/workflows/README.md) for workflow help

## Phase 10: Team Communication (5 minutes)

- [ ] Document deployment process for team
- [ ] Share CICD_QUICKSTART.md with team
- [ ] Set up on-call rotation
- [ ] Create incident response runbook

## Troubleshooting

### Issue: GitHub Actions Secret Not Working
**Solution**: 
1. Verify secret names exactly match workflow files
2. Re-create secret if unsure
3. Secrets are case-sensitive

### Issue: ArgoCD Cannot Connect to GKE
**Solution**:
1. Verify `ARGOCD_SERVER` URL is correct
2. Check `ARGOCD_AUTH_TOKEN` is valid: `argocd account list`
3. Verify token permissions: `argocd account get-tokens admin`

### Issue: Pods Not Starting
**Solution**:
1. Check logs: `kubectl logs -n adk-agents -l app=adk-agents --tail=100`
2. Check events: `kubectl describe pod -n adk-agents <pod-name>`
3. Check resource limits: `kubectl top pods -n adk-agents`

### Issue: Metrics Not Showing in Prometheus
**Solution**:
1. Verify ServiceMonitor created: `kubectl get servicemonitor -n adk-agents`
2. Check Prometheus targets: http://localhost:9090/targets
3. Verify scrape interval (usually 30s)

## Rollback Plan

If anything goes wrong:

```bash
# Rollback application deployment
argocd app rollback adk-agents-staging

# Or manually:
kubectl rollout undo deployment/adk-agents -n adk-agents

# Delete and reinstall ArgoCD if needed
kubectl delete namespace argocd
# Then repeat Phase 4
```

## Success Criteria

✅ Setup is complete when:

1. [ ] GitHub Actions workflows running successfully
2. [ ] Docker images building and pushing to registry
3. [ ] ArgoCD syncing applications
4. [ ] Staging deployment has healthy pods
5. [ ] Production deployment (if applicable) with canary working
6. [ ] Prometheus metrics being collected
7. [ ] Feature flags service responding
8. [ ] Team can deploy using the documented process

## Next Steps

1. Run through [CICD_QUICKSTART.md](./CICD_QUICKSTART.md) with team
2. Document any customizations made
3. Set up monitoring alerts
4. Schedule team training on deployment procedures
5. Test rollback procedures
6. Monitor first few deployments closely

---

**Estimated Total Time**: 1.5 - 2.5 hours

**Most Common Delays**:
- WIF setup (if unfamiliar)
- ArgoCD initial setup
- Waiting for pods to start

**Support**: Refer to [CI_CD_SETUP.md](./CI_CD_SETUP.md) troubleshooting section
