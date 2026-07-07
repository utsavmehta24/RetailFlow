Write-Host "=== Starting RetailFlow Environment Teardown ===" -ForegroundColor Yellow

$binDir = Join-Path $PSScriptRoot "..\bin"
$tfPath = Join-Path $binDir "terraform.exe"
$infraDir = Join-Path $PSScriptRoot "..\infra"

# 1. Run terraform destroy
if (Test-Path $tfPath) {
    Write-Host "Destroying Terraform provisioned resources..."
    $destroyProcess = Start-Process -FilePath $tfPath -ArgumentList "destroy -auto-approve" -WorkingDirectory $infraDir -NoNewWindow -PassThru -Wait
    if ($destroyProcess.ExitCode -ne 0) {
        Write-Warning "Terraform destroy encountered an error or was not fully clean."
    }
} else {
    Write-Warning "Terraform binary not found. Skipping resource destruction."
}

# 2. Stop and remove Docker containers and volumes
Write-Host "Stopping and destroying Docker containers and volumes..."
docker compose down -v

Write-Host "=== Teardown completed successfully! ===" -ForegroundColor Green
