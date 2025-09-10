# Import Hackathon Dashboard to Grafana
# This script imports the dashboard via Grafana API

$dashboardPath = "grafana\dashboards\ai-rate-limiter-hackathon.json"
$grafanaUrl = "http://localhost:3000"
$username = "admin"
$password = "admin"

Write-Host "Importing Hackathon Dashboard to Grafana..." -ForegroundColor Cyan

# Read the dashboard JSON
try {
    $dashboardContent = Get-Content -Path $dashboardPath -Raw | ConvertFrom-Json
    Write-Host "[OK] Dashboard JSON loaded successfully" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Failed to read dashboard JSON: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Prepare the import payload
$importPayload = @{
    dashboard = $dashboardContent
    overwrite = $true
    inputs = @()
} | ConvertTo-Json -Depth 10

# Create credentials for basic auth
$base64AuthInfo = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${username}:${password}"))
$headers = @{
    "Authorization" = "Basic $base64AuthInfo"
    "Content-Type" = "application/json"
}

# Import the dashboard
try {
    $response = Invoke-WebRequest -Uri "$grafanaUrl/api/dashboards/db" -Method POST -Body $importPayload -Headers $headers -UseBasicParsing
    
    if ($response.StatusCode -eq 200) {
        $result = $response.Content | ConvertFrom-Json
        Write-Host "[SUCCESS] Dashboard imported successfully!" -ForegroundColor Green
        Write-Host "Dashboard URL: $grafanaUrl/d/$($result.uid)" -ForegroundColor White
        Write-Host "Dashboard ID: $($result.id)" -ForegroundColor White
    } else {
        Write-Host "[ERROR] Import failed with status: $($response.StatusCode)" -ForegroundColor Red
        Write-Host $response.Content -ForegroundColor Yellow
    }
} catch {
    if ($_.Exception.Response.StatusCode -eq 401) {
        Write-Host "[ERROR] Authentication failed. Using default credentials admin/admin" -ForegroundColor Red
        Write-Host "Please verify Grafana is accessible at $grafanaUrl" -ForegroundColor Yellow
    } else {
        Write-Host "[ERROR] Failed to import dashboard: $($_.Exception.Message)" -ForegroundColor Red
        if ($_.ErrorDetails.Message) {
            Write-Host "Details: $($_.ErrorDetails.Message)" -ForegroundColor Yellow
        }
    }
}

Write-Host ""
Write-Host "Manual Steps:" -ForegroundColor Cyan
Write-Host "1. Open Grafana: $grafanaUrl" -ForegroundColor White
Write-Host "2. Login with: admin/admin" -ForegroundColor White
Write-Host "3. Go to '+' -> Import" -ForegroundColor White
Write-Host "4. Upload: $dashboardPath" -ForegroundColor White
