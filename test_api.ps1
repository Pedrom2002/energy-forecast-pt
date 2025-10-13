# PowerShell script to test Energy Forecast PT API
# Usage: .\test_api.ps1

$API_URL = "http://localhost:8000"

Write-Host "`n==================================" -ForegroundColor Cyan
Write-Host "Energy Forecast PT - API Tests" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan

# Test 1: Root endpoint
Write-Host "`n[1] Testing GET / ..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$API_URL/" -Method Get
    Write-Host "✓ Success!" -ForegroundColor Green
    $response | ConvertTo-Json
} catch {
    Write-Host "✗ Failed: $_" -ForegroundColor Red
}

# Test 2: Health check
Write-Host "`n[2] Testing GET /health ..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$API_URL/health" -Method Get
    Write-Host "✓ Success!" -ForegroundColor Green
    $response | ConvertTo-Json
} catch {
    Write-Host "✗ Failed: $_" -ForegroundColor Red
}

# Test 3: Get regions
Write-Host "`n[3] Testing GET /regions ..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$API_URL/regions" -Method Get
    Write-Host "✓ Success!" -ForegroundColor Green
    $response | ConvertTo-Json
} catch {
    Write-Host "✗ Failed: $_" -ForegroundColor Red
}

# Test 4: Get model info
Write-Host "`n[4] Testing GET /model/info ..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$API_URL/model/info" -Method Get
    Write-Host "✓ Success!" -ForegroundColor Green
    $response | ConvertTo-Json -Depth 10
} catch {
    Write-Host "✗ Failed: $_" -ForegroundColor Red
}

# Test 5: Single prediction
Write-Host "`n[5] Testing POST /predict ..." -ForegroundColor Yellow
try {
    $body = @{
        timestamp = "2025-01-15T14:00:00"
        region = "Lisboa"
        temperature = 18.5
        humidity = 65.0
        wind_speed = 12.3
        precipitation = 0.0
        cloud_cover = 40.0
        pressure = 1015.0
    } | ConvertTo-Json

    $response = Invoke-RestMethod -Uri "$API_URL/predict" `
        -Method Post `
        -ContentType "application/json" `
        -Body $body

    Write-Host "✓ Success!" -ForegroundColor Green
    Write-Host "Predicted Consumption: $($response.predicted_consumption_mw) MW" -ForegroundColor Cyan
    Write-Host "Confidence Interval: [$($response.confidence_interval_lower), $($response.confidence_interval_upper)] MW" -ForegroundColor Cyan
    Write-Host "Model: $($response.model_name)" -ForegroundColor Cyan
    $response | ConvertTo-Json
} catch {
    Write-Host "✗ Failed: $_" -ForegroundColor Red
}

# Test 6: Batch prediction
Write-Host "`n[6] Testing POST /predict/batch ..." -ForegroundColor Yellow
try {
    $body = @(
        @{
            timestamp = "2025-01-15T14:00:00"
            region = "Lisboa"
            temperature = 18.5
            humidity = 65.0
            wind_speed = 12.3
            precipitation = 0.0
            cloud_cover = 40.0
            pressure = 1015.0
        },
        @{
            timestamp = "2025-01-15T15:00:00"
            region = "Norte"
            temperature = 16.0
            humidity = 70.0
            wind_speed = 15.0
            precipitation = 0.5
            cloud_cover = 60.0
            pressure = 1012.0
        }
    ) | ConvertTo-Json

    $response = Invoke-RestMethod -Uri "$API_URL/predict/batch" `
        -Method Post `
        -ContentType "application/json" `
        -Body $body

    Write-Host "✓ Success!" -ForegroundColor Green
    Write-Host "Total Predictions: $($response.total_predictions)" -ForegroundColor Cyan
    $response | ConvertTo-Json -Depth 10
} catch {
    Write-Host "✗ Failed: $_" -ForegroundColor Red
}

# Test 7: Get limitations
Write-Host "`n[7] Testing GET /limitations ..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$API_URL/limitations" -Method Get
    Write-Host "✓ Success!" -ForegroundColor Green
    $response | ConvertTo-Json -Depth 10
} catch {
    Write-Host "✗ Failed: $_" -ForegroundColor Red
}

Write-Host "`n==================================" -ForegroundColor Cyan
Write-Host "All tests completed!" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host "`nAPI Documentation: $API_URL/docs" -ForegroundColor Yellow
Write-Host "ReDoc: $API_URL/redoc`n" -ForegroundColor Yellow
