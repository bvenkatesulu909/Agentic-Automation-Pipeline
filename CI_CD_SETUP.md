# CI/CD Setup Guide - ADK Agents

This document provides a complete setup guide for the CI/CD pipeline using GitHub Actions and ArgoCD.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [GitHub Actions Setup](#github-actions-setup)
4. [ArgoCD Installation & Configuration](#argocd-installation--configuration)
5. [Canary Deployments](#canary-deployments)
6. [Feature Flags](#feature-flags)
7. [Monitoring & Alerts](#monitoring--alerts)
8. [Troubleshooting](#troubleshooting)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      GitHub Repository                      │
│  ┌─────────────────────────────────────────────────────────┐│
│  │          GitHub Actions Workflows                       ││
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐              ││
│  │  │   CI     │→ │  BUILD   │→ │   TEST   │              ││
│  │  └──────────┘  └──────────┘  └──────────┘              ││
│  │                        ↓                                ││
│  │         Push to Google Artifact Registry               ││
│  │                        ↓                                ││
│  │     Update k8s/overlays/* with new image tag           ││
│  │                        ↓                                ││
│  │              Trigger ArgoCD Sync                        ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Google Cloud / GKE                        │
│  ┌──────────────────────────────────────────────────────────┐│
│  │                 ArgoCD on GKE                            ││
│  │  ┌─────────────────────────────────────────────────────┐││
│  │  │  Application Controllers                            │││
│  │  │  - Staging: develop branch                          │││
│  │  │  - Production: main branch with canary              │││
│  │  └─────────────────────────────────────────────────────┘││
│  │                        ↓                                ││
│  │  ┌─────────────────────────────────────────────────────┐││
│  │  │      Kustomize Overlays (Environment Config)        │││
│  │  │  - base/: Common configuration                      │││
│  │  │  - overlays/staging/: Low resources, 1 replica     │││
│  │  │  - overlays/production/: HA, 3 replicas, canary   │││
│  │  └─────────────────────────────────────────────────────┘││
│  │                        ↓                                ││
│  │  ┌─────────────────────────────────────────────────────┐││
│  │  │    Deployments with Health Checks & Metrics         │││
│  │  │  ┌─────────────┐  ┌─────────────┐                  │││
│  │  │  │   Staging   │  │  Production │                  │││
│  │  │  │   1 replica │  │  3 replicas │                  │││
│  │  │  └─────────────┘  └─────────────┘                  │││
│  │  └─────────────────────────────────────────────────────┘││
│  │                                                          ││
│  │  ┌──────────────────────────────────────────────────────┐││
│  │  │         Flagger Canary Controller                    │││
│  │  │  (Production Only)                                   │││
│  │  │  - Progressive rollout: 10% → 20% → 50% → 100%     │││
│  │  │  - Continuous metric analysis                        │││
│  │  │  - Automatic rollback on SLO violation              │││
│  │  └──────────────────────────────────────────────────────┘││
│  │                                                          ││
│  │  ┌──────────────────────────────────────────────────────┐││
│  │  │    Prometheus + AlertManager for Quality Gates      │││
│  │  │  - Error rate: < 5%                                 │││
│  │  │  - Latency P95: < 2s                                │││
│  │  │  - Memory: < 80%                                    │││
│  │  │  - CPU: < 80%                                       │││
│  │  └──────────────────────────────────────────────────────┘││
│  └──────────────────────────────────────────────────────────┘│
│                                                               │
│  ┌──────────────────────────────────────────────────────────┐│
│  │       Feature Flags Service (adk-agents namespace)      ││
│  │  - Controls feature rollouts                             ││
│  │  - Supports gradual enablement                           ││
│  │  - Per-user and environment targeting                    ││
│  └──────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

### Required Tools
- `kubectl` (v1.24+)
- `argocd` CLI (for manual deployments)
- `gcloud` CLI (GCP authentication)
- Docker (for local testing)
- `kustomize` (for K8s manifest templating)

### GCP Setup
1. GKE cluster(s) running:
   - `adk-staging-cluster` in `us-west1`
   - `adk-prod-cluster` in `us-west1`

2. Artifact Registry:
   - `us-west1-docker.pkg.dev/venkatesh-68cb677e/adk/`

3. Service Account with permissions:
   - GKE cluster access
   - Artifact Registry push/pull
   - Workload Identity configured

### GitHub Repository Setup
1. Repository secrets configured
2. Workflows enabled
3. Branch protection rules on `main` and `develop`

## GitHub Actions Setup

### 1. Configure GitHub Secrets

Add these secrets to your GitHub repository (Settings → Secrets and variables → Actions):

```bash
# GCP Workload Identity Federation
WIF_PROVIDER=<your-workload-identity-provider>
WIF_SERVICE_ACCOUNT=<your-service-account>@<your-project>.iam.gserviceaccount.com

# ArgoCD
ARGOCD_SERVER=argocd.<your-domain>.com  # e.g., argocd.example.com
ARGOCD_AUTH_TOKEN=<argocd-token>        # Generated from ArgoCD

# Security Scanning
GITGUARDIAN_API_KEY=<your-gitguardian-key>
```

### 2. Set Up Workload Identity Federation

```bash
# Create a Google Cloud service account
gcloud iam service-accounts create github-actions \
  --display-name="GitHub Actions CI/CD"

# Grant necessary roles
gcloud projects add-iam-policy-binding venkatesh-68cb677e \
  --member="serviceAccount:github-actions@venkatesh-68cb677e.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding venkatesh-68cb677e \
  --member="serviceAccount:github-actions@venkatesh-68cb677e.iam.gserviceaccount.com" \
  --role="roles/container.developer"

# Create Workload Identity Federation pool
gcloud iam workload-identity-pools create "github-actions" \
  --location=global \
  --display-name="GitHub Actions"

# Get the pool resource name
WORKLOAD_IDENTITY_POOL_ID=$(gcloud iam workload-identity-pools describe \
  "github-actions" --location=global --format='value(name)')

# Create a workload identity provider
gcloud iam workload-identity-pools providers create-oidc "github" \
  --location=global \
  --workload-identity-pool="github-actions" \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,assertion.aud=assertion.aud,assertion.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-condition="assertion.repository == 'your-org/your-repo'"

# Create service account impersonation binding
gcloud iam service-accounts add-iam-policy-binding \
  "github-actions@venkatesh-68cb677e.iam.gserviceaccount.com" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/locations/global/workloadIdentityPools/github-actions/attribute.repository/your-org/your-repo"
```

### 3. Configure Branch Protection Rules

On GitHub, set up branch protection for `main`:
- ✅ Require status checks to pass before merging (CI, Build, Test)
- ✅ Dismiss stale pull request approvals
- ✅ Require code reviews before merging
- ✅ Require branches to be up to date before merging

## ArgoCD Installation & Configuration

### 1. Install ArgoCD on Staging Cluster

```bash
# Create namespace
kubectl create namespace argocd

# Install ArgoCD
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for all pods to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=argocd-server \
  -n argocd --timeout=300s
```

### 2. Install ArgoCD on Production Cluster

```bash
# Repeat the above commands on the production cluster
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

### 3. Configure ArgoCD Server Access

```bash
# Get the ArgoCD admin password
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d

# Port forward to access UI
kubectl port-forward -n argocd svc/argocd-server 8080:443

# Access at: https://localhost:8080
# Username: admin
# Password: <output from above>

# Change admin password (recommended)
argocd account update-password --account admin --new-password <new-password>

# Create API token for CI/CD
argocd account generate-token --account cicd-user
```

### 4. Create ArgoCD Applications

```bash
# Apply ArgoCD application manifests
kubectl apply -f k8s/argocd/namespace.yaml
kubectl apply -f k8s/argocd/apps/adk-agents-staging.yaml
kubectl apply -f k8s/argocd/apps/adk-agents-production.yaml

# Verify applications are synced
argocd app get adk-agents-staging
argocd app get adk-agents-production
```

### 5. Set Up Webhook for GitHub

```bash
# Get ArgoCD server URL
ARGOCD_URL=$(kubectl -n argocd get svc argocd-server -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

# Add webhook to your GitHub repository:
# Go to Settings → Webhooks → Add webhook
# Payload URL: https://<ARGOCD_URL>/api/webhook
# Content type: application/json
# Events: Push events
```

## Canary Deployments

### How It Works

1. **New version is deployed to canary** (10% traffic)
2. **Metrics are analyzed** for 5-10 minutes
3. **If metrics pass**, traffic increases to 20%, then 50%, then 100%
4. **If metrics fail**, automatic rollback to previous stable version

### Quality Gates (SLOs)

```yaml
Error Rate:     < 5%
Latency P95:    < 2 seconds
Memory Usage:   < 80%
CPU Usage:      < 80%
Pod Restarts:   0 in 15 minutes
```

### Install Flagger & Prometheus

```bash
# Add Flagger Helm repo
helm repo add flagger https://flagger.app
helm repo update

# Install Flagger on production cluster
helm install flagger flagger/flagger \
  --namespace flagger-system \
  --create-namespace \
  --set prometheus.install=true

# Install Flagger LoadTester for synthetic testing
helm install flagger-loadtester flagger/loadtester \
  --namespace flagger-system
```

### Monitor Canary Progress

```bash
# Watch canary status
kubectl get canary -n adk-agents -w

# Get detailed status
kubectl describe canary adk-agents -n adk-agents

# View canary events
kubectl logs -n flagger-system deployment/flagger

# Check Prometheus metrics
kubectl port-forward -n monitoring svc/prometheus 9090:9090
# Visit: http://localhost:9090/graph?query=adk_agents:request_error_rate_5m
```

### Manual Rollback (if needed)

```bash
# Rollback to previous version
kubectl rollout undo deployment/adk-agents -n adk-agents

# Verify rollback
kubectl rollout status deployment/adk-agents -n adk-agents
```

## Feature Flags

### Deploying Feature Flags Service

```bash
# The feature flags service is deployed as part of the base configuration
kubectl apply -f k8s/feature-flags/deployment.yaml

# Verify deployment
kubectl get pods -n adk-agents -l app=feature-flags

# Check service
kubectl get svc -n adk-agents feature-flags
```

### Using Feature Flags in Your Code

```python
import httpx
import os

async def get_feature_flags(user_id: str = None):
    """Fetch feature flags from the feature flags service."""
    url = os.getenv("FEATURE_FLAGS_ENDPOINT", "http://feature-flags:8080/api/flags")
    async with httpx.AsyncClient() as client:
        params = {
            "environment": os.getenv("ENVIRONMENT", "production"),
        }
        if user_id:
            params["user_id"] = user_id
        
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()

async def is_feature_enabled(flag_name: str, user_id: str = None):
    """Check if a feature is enabled."""
    flags = await get_feature_flags(user_id)
    for flag in flags.get("flags", []):
        if flag["name"] == flag_name:
            return flag["enabled"]
    return False
```

### Updating Rollout Percentages

```bash
# Start rolling out a new feature to 50% of users
curl -X POST http://feature-flags:8080/api/flags/enable_new_router/rollout?percentage=50

# Get current rollout status
curl http://feature-flags:8080/api/flags/enable_new_router

# Complete rollout to 100%
curl -X POST http://feature-flags:8080/api/flags/enable_new_router/rollout?percentage=100
```

## Monitoring & Alerts

### Access Prometheus

```bash
# Port forward to Prometheus
kubectl port-forward -n monitoring svc/prometheus 9090:9090

# Visit: http://localhost:9090
```

### Key Metrics to Monitor

```promql
# Error rate
adk_agents:request_error_rate_5m

# P95 latency
adk_agents:request_latency_p95

# P99 latency
adk_agents:request_latency_p99

# Memory usage percentage
adk_agents:memory_usage_percent

# CPU usage percentage
adk_agents:cpu_usage_percent

# Request success rate
adk_agents:request_success_rate
```

### Alert Rules

Alerts are defined in `k8s/monitoring/prometheus-rules.yaml` and include:
- High error rate (>5%)
- High latency (P95 > 2s)
- High memory usage (>80%)
- High CPU usage (>80%)
- Pod crash looping

### Receiving Alerts

Configure AlertManager to send alerts to:
- Slack
- Email
- PagerDuty
- Custom webhooks

Example AlertManager config:
```bash
kubectl create secret generic alertmanager-config \
  --from-file=alertmanager.yml \
  -n monitoring
```

## Troubleshooting

### GitHub Actions Workflow Fails

**Check logs:**
```bash
# View workflow logs in GitHub UI
# Settings → Actions → [Workflow Name] → [Run]
```

**Common issues:**
- Secrets not configured → Add missing secrets to GitHub
- Authentication failed → Verify WIF credentials
- Docker build failed → Check Dockerfile and dependencies

### ArgoCD Application Out of Sync

```bash
# Check sync status
argocd app sync adk-agents-production

# Force sync
argocd app sync adk-agents-production --force

# Check application details
kubectl get application adk-agents-production -n argocd -o yaml
```

### Canary Deployment Stuck

```bash
# Check canary status
kubectl describe canary adk-agents -n adk-agents

# Check Flagger logs
kubectl logs -n flagger-system -l app=flagger

# Check metrics provider connectivity
kubectl exec -n monitoring prometheus-0 -- promtool query instant 'up'

# Manual promote if needed
kubectl patch canary adk-agents -n adk-agents -p \
  '{"metadata":{"finalizers":null}}' --type=merge
```

### High Memory/CPU Usage

```bash
# Check resource usage
kubectl top pods -n adk-agents

# Check deployment limits
kubectl get deployment adk-agents -n adk-agents -o yaml | grep -A 5 resources:

# Scale down if needed
kubectl scale deployment adk-agents -n adk-agents --replicas=1
```

### Pods Not Starting

```bash
# Check pod status
kubectl describe pod -n adk-agents -l app=adk-agents

# View logs
kubectl logs -n adk-agents -l app=adk-agents --tail=100

# Check image pull
kubectl get events -n adk-agents --sort-by='.lastTimestamp'
```

## Next Steps

1. **Customize metrics thresholds** in `k8s/monitoring/prometheus-rules.yaml`
2. **Set up notification channels** for alerts
3. **Configure automatic scaling** based on metrics
4. **Add more feature flags** for gradual rollouts
5. **Set up cost monitoring** for GKE clusters
6. **Document deployment procedures** for your team

## Additional Resources

- [ArgoCD Documentation](https://argo-cd.readthedocs.io/)
- [Flagger Documentation](https://flagger.app/)
- [Kustomize Documentation](https://kustomize.io/)
- [GitHub Actions Documentation](https://docs.github.com/actions)
- [GKE Best Practices](https://cloud.google.com/kubernetes-engine/docs/best-practices)
