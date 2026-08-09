#!/bin/bash
# Quick start script for observability stack

set -e

echo "🚀 Starting Real-Time Observability Stack..."
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker found${NC}"
echo ""

# Start containers
echo "📦 Starting Docker containers..."
docker-compose -f docker-compose.observability.yml up -d

echo ""
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check services
echo ""
echo "🔍 Checking services..."

services=(
    "prometheus:9090"
    "grafana:3000"
    "jaeger:16686"
    "alertmanager:9093"
)

for service in "${services[@]}"; do
    IFS=':' read -r name port <<< "$service"
    if curl -s http://localhost:$port > /dev/null 2>&1; then
        echo -e "${GREEN}✓ $name ($port)${NC}"
    else
        echo -e "${YELLOW}⚠ $name ($port) - not ready yet${NC}"
    fi
done

echo ""
echo "📊 Observability Stack is Running!"
echo ""
echo "Access points:"
echo -e "  ${GREEN}Grafana${NC}        http://localhost:3000 (admin/admin)"
echo -e "  ${GREEN}Prometheus${NC}     http://localhost:9090"
echo -e "  ${GREEN}Jaeger${NC}         http://localhost:16686"
echo -e "  ${GREEN}AlertManager${NC}   http://localhost:9093"
echo ""

echo "📚 Next steps:"
echo "  1. Install Python dependencies:"
echo "     pip install -r observability_requirements.txt"
echo ""
echo "  2. Start example app:"
echo "     python -m src.observability.example_app"
echo ""
echo "  3. Generate test traffic:"
echo "     curl http://localhost:5000/api/data"
echo ""
echo "  4. View setup guide:"
echo "     cat OBSERVABILITY_SETUP_GUIDE.md"
echo ""

echo -e "${YELLOW}💡 Tip: Logs are available with 'docker-compose -f docker-compose.observability.yml logs -f'${NC}"
