# 🏆 Hackathon Setup Script - Windows PowerShell Edition
# Get everything running in 2 minutes!

Write-Host "HACKATHON AI RATE LIMITER - QUICK START" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
try {
    docker info | Out-Null
    Write-Host "[OK] Docker is running" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Docker is not running. Please start Docker Desktop and try again." -ForegroundColor Red
    exit 1
}

# Check Docker Compose
$composeCmd = $null
if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
    $composeCmd = "docker-compose"
} elseif ((docker compose version 2>&1) -match "version") {
    $composeCmd = "docker compose"
} else {
    Write-Host "[ERROR] Docker Compose not found. Please install Docker Compose." -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Docker Compose found: $composeCmd" -ForegroundColor Green
Write-Host ""

# Stop existing containers
Write-Host "Cleaning up existing containers..." -ForegroundColor Yellow
& $composeCmd.Split() down -v 2>$null

# Build and start services
Write-Host "Building and starting services..." -ForegroundColor Cyan
& $composeCmd.Split() up -d --build

Write-Host ""
Write-Host "Waiting for services to be ready..." -ForegroundColor Yellow
Start-Sleep 15

# Health check function
function Test-Service {
    param($Name, $Url)
    
    Write-Host "   Checking $Name ($Url)... " -NoNewline
    
    for ($i = 1; $i -le 30; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -Method GET -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                Write-Host "[READY]" -ForegroundColor Green
                return $true
            }
        } catch {
            Start-Sleep 1
        }
    }
    
    Write-Host "[NOT READY] (continuing)" -ForegroundColor Yellow
    return $false
}

Write-Host ""
Write-Host "Service Health Check:" -ForegroundColor Cyan
Test-Service "Backend" "http://localhost:8000/health"
Test-Service "AI Limiter" "http://localhost:8080/health"
Test-Service "Grafana" "http://localhost:3000"
Test-Service "Prometheus" "http://localhost:9090/-/ready"

Write-Host ""
Write-Host "Setting up demo data..." -ForegroundColor Yellow

# Initialize services
try {
    Invoke-WebRequest -Uri "http://localhost:8080/admin/init" -Method POST -UseBasicParsing | Out-Null
} catch {
    Write-Host "Warning: Init failed (continuing)" -ForegroundColor Yellow
}

try {
    Invoke-WebRequest -Uri "http://localhost:8080/api/demo/reset" -Method POST -UseBasicParsing | Out-Null
} catch {
    Write-Host "Warning: Reset failed (continuing)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "HACKATHON SETUP COMPLETE!" -ForegroundColor Green -BackgroundColor Black
Write-Host "=========================" -ForegroundColor Green -BackgroundColor Black
Write-Host ""
Write-Host "Demo URLs:" -ForegroundColor Cyan
Write-Host "   AI Limiter API:    http://localhost:8080" -ForegroundColor White
Write-Host "   Grafana Dashboard: http://localhost:3000" -ForegroundColor White
Write-Host "   Prometheus:        http://localhost:9090" -ForegroundColor White
Write-Host "   Backend Service:   http://localhost:8000" -ForegroundColor White
Write-Host ""
Write-Host "Demo Commands:" -ForegroundColor Cyan
Write-Host "   Load Generator:       python load_generator.py --demo" -ForegroundColor White
Write-Host "   Single Scenario:      python load_generator.py --scenario blackfriday" -ForegroundColor White
Write-Host "   Health Check:         python load_generator.py --check" -ForegroundColor White
Write-Host ""
Write-Host "Grafana Login: admin/admin (change on first login)" -ForegroundColor Yellow
Write-Host ""
Write-Host "Ready for hackathon demo! Run the load generator to see AI in action." -ForegroundColor Green
Write-Host ""
Write-Host "Pro tip: Run 'python load_generator.py --demo' in another terminal" -ForegroundColor Magenta
Write-Host "and watch the AI make intelligent rate limiting decisions in real-time!" -ForegroundColor Magenta
