#!/bin/bash
# Deployment script for vLLM inference server on Kubernetes
# Usage: ./deploy.sh [dev|staging|prod]

set -e

ENVIRONMENT="${1:-dev}"
PROJECT_ID="your-project-id"
REGION="us-central1"
CLUSTER_NAME="inference-cluster"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ============================================================================
# Prerequisites Check
# ============================================================================

log_info "Checking prerequisites..."

# Check if kubectl is installed
if ! command -v kubectl &> /dev/null; then
    log_error "kubectl is not installed"
    exit 1
fi

# Check if gcloud is installed (for GKE)
if ! command -v gcloud &> /dev/null; then
    log_error "gcloud CLI is not installed"
    exit 1
fi

# Check if kustomize is installed
if ! command -v kustomize &> /dev/null; then
    log_warn "kustomize is not installed, installing..."
    curl -s "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh" | bash
    sudo mv kustomize /usr/local/bin/
fi

log_info "✓ All prerequisites satisfied"

# ============================================================================
# GKE Cluster Setup
# ============================================================================

log_info "Configuring GKE cluster access..."

gcloud container clusters get-credentials "$CLUSTER_NAME" \
    --region "$REGION" \
    --project "$PROJECT_ID"

CURRENT_CONTEXT=$(kubectl config current-context)
log_info "✓ Connected to cluster: $CURRENT_CONTEXT"

# ============================================================================
# Build and Push Docker Image
# ============================================================================

log_info "Building and pushing Docker image..."

DOCKER_REGISTRY="us.gcr.io/$PROJECT_ID"
IMAGE_NAME="inference-server"
IMAGE_TAG="v1.0.0"
IMAGE_FULL="$DOCKER_REGISTRY/$IMAGE_NAME:$IMAGE_TAG"

# Build image
docker build -t "$IMAGE_FULL" .

# Push to GCR
docker push "$IMAGE_FULL"
log_info "✓ Image pushed to $IMAGE_FULL"

# ============================================================================
# Deploy with Kustomize
# ============================================================================

log_info "Deploying inference server with Kustomize..."

# Update image in kustomization
kustomize edit set image "us.gcr.io/your-project/inference-server=$IMAGE_FULL"

# Apply kustomization
kubectl apply -k .

log_info "✓ Deployment manifests applied"

# ============================================================================
# Wait for Deployment
# ============================================================================

log_info "Waiting for deployment to be ready..."

kubectl rollout status deployment/inference-server \
    --namespace=default \
    --timeout=10m

log_info "✓ Deployment is ready"

# ============================================================================
# Verify Deployment
# ============================================================================

log_info "Verifying deployment..."

# Get pod information
PODS=$(kubectl get pods -l app=inference-server -o name)
log_info "Inference server pods:"
kubectl get pods -l app=inference-server -o wide

# Check pod logs for errors
for POD in $PODS; do
    log_info "Checking logs for $POD..."
    kubectl logs "$POD" --tail=50 | head -20 || true
done

# ============================================================================
# Port Forwarding (for local testing)
# ============================================================================

log_info "Setting up port forwarding..."
log_info "Run this to access the server locally:"
log_info "kubectl port-forward svc/inference-server 8000:8000 &"
log_info ""

# ============================================================================
# Monitoring Setup
# ============================================================================

log_info "Checking monitoring stack..."

if kubectl get namespace monitoring &> /dev/null; then
    log_info "✓ Monitoring namespace exists"
    log_info "Prometheus: kubectl port-forward -n monitoring svc/prometheus 9090:9090"
    log_info "Grafana: kubectl port-forward -n monitoring svc/grafana 3000:3000"
else
    log_warn "Monitoring namespace not found. Install Prometheus/Grafana for metrics."
fi

# ============================================================================
# Summary
# ============================================================================

log_info ""
log_info "=========================================="
log_info "Deployment Complete!"
log_info "=========================================="
log_info "Environment: $ENVIRONMENT"
log_info "Cluster: $CURRENT_CONTEXT"
log_info "Image: $IMAGE_FULL"
log_info "Replicas: $(kubectl get deployment inference-server -o jsonpath='{.spec.replicas}')"
log_info ""
log_info "Next steps:"
log_info "1. Test the server: curl http://inference-server:8000/health"
log_info "2. Monitor: kubectl logs -f deployment/inference-server"
log_info "3. Scale: kubectl scale deployment inference-server --replicas=5"
log_info "=========================================="

exit 0
