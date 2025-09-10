#!/usr/bin/env bash
# 🏆 Hackathon Setup Script - Get everything running in 2 minutes!

set -e

echo "🏆 HACKATHON AI RATE LIMITER - QUICK START"
echo "========================================="
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop and try again."
    exit 1
fi

echo "✅ Docker is running"

# Check if docker-compose is available
if command -v docker-compose > /dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
elif docker compose version > /dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
else
    echo "❌ Docker Compose not found. Please install Docker Compose."
    exit 1
fi

echo "✅ Docker Compose found: $COMPOSE_CMD"
echo ""

# Stop any existing containers
echo "🧹 Cleaning up existing containers..."
$COMPOSE_CMD down -v > /dev/null 2>&1 || true

# Build and start services
echo "🚀 Building and starting services..."
$COMPOSE_CMD up -d --build

echo ""
echo "⏳ Waiting for services to be ready..."
sleep 15

# Check service health
check_service() {
    local name=$1
    local url=$2
    local port=$3
    
    echo -n "   Checking $name ($url)... "
    
    # Wait up to 30 seconds for service
    for i in {1..30}; do
        if curl -sf "$url" > /dev/null 2>&1; then
            echo "✅ Ready"
            return 0
        fi
        sleep 1
    done
    
    echo "⚠️  Not ready (but continuing)"
    return 1
}

echo ""
echo "🔍 Service Health Check:"
check_service "Backend" "http://localhost:8000/health" 8000
check_service "AI Limiter" "http://localhost:8080/health" 8080
check_service "Grafana" "http://localhost:3000" 3000
check_service "Prometheus" "http://localhost:9090/-/ready" 9090

echo ""
echo "🎯 Setting up demo data..."

# Initialize the rate limiter
curl -sf -X POST http://localhost:8080/admin/init > /dev/null || echo "⚠️  Init failed (continuing)"

# Reset demo state
curl -sf -X POST http://localhost:8080/api/demo/reset > /dev/null || echo "⚠️  Reset failed (continuing)"

echo ""
echo "🏆 HACKATHON SETUP COMPLETE!"
echo "=========================="
echo ""
echo "🎪 Demo URLs:"
echo "   🤖 AI Limiter API:    http://localhost:8080"
echo "   📊 Grafana Dashboard: http://localhost:3000"
echo "   🔍 Prometheus:        http://localhost:9090"
echo "   🖥️  Backend Service:   http://localhost:8000"
echo ""
echo "🎬 Demo Commands:"
echo "   Load Generator:       python load_generator.py --demo"
echo "   Single Scenario:      python load_generator.py --scenario blackfriday"
echo "   Health Check:         python load_generator.py --check"
echo ""
echo "🔑 Grafana Login: admin/admin (change on first login)"
echo ""
echo "🚀 Ready for hackathon demo! Run the load generator to see AI in action."
echo ""

# Make script executable
chmod +x hackathon_demo.py 2>/dev/null || true
chmod +x load_generator.py 2>/dev/null || true

echo "💡 Pro tip: Run 'python load_generator.py --demo' in another terminal"
echo "    and watch the AI make intelligent rate limiting decisions in real-time!"
