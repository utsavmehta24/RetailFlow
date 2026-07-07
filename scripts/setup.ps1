Write-Host "=== Starting RetailFlow Environment Setup ===" -ForegroundColor Green

# 1. Spin up Docker containers
Write-Host "Spinning up Docker containers (LocalStack & Postgres)..."
docker compose up -d

# 2. Bootstrap Terraform binary if not present
$binDir = Join-Path $PSScriptRoot "..\bin"
$tfPath = Join-Path $binDir "terraform.exe"

if (-not (Test-Path $tfPath)) {
    Write-Host "Terraform binary not found. Downloading Terraform v1.9.2..."
    New-Item -ItemType Directory -Force -Path $binDir | Out-Null
    $zipPath = Join-Path $binDir "terraform.zip"
    $downloadUrl = "https://releases.hashicorp.com/terraform/1.9.2/terraform_1.9.2_windows_amd64.zip"
    
    # Set Security Protocol to TLS 1.2
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $downloadUrl -OutFile $zipPath
    
    Write-Host "Extracting Terraform..."
    Expand-Archive -Path $zipPath -DestinationPath $binDir -Force
    Remove-Item $zipPath
    Write-Host "Terraform downloaded and installed locally under: $tfPath"
}

# 3. Wait for LocalStack S3 to be healthy
Write-Host "Waiting for LocalStack S3 to start..."
$localstackUrl = "http://127.0.0.1:4566/"
$maxRetries = 30
$retryCount = 0
$healthy = $false

while (-not $healthy -and $retryCount -lt $maxRetries) {
    try {
        $response = Invoke-WebRequest -Uri $localstackUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($response.StatusCode -eq 200 -or $response.StatusCode -eq 404) {
            # 200 or 404 means the port is open and responding (S3 index returns 404 sometimes, which is fine)
            $healthy = $true
        }
    } catch {
        # Ignore errors and retry
    }
    if (-not $healthy) {
        $retryCount++
        Start-Sleep -Seconds 2
        Write-Host "Waiting for LocalStack... ($retryCount/$maxRetries)"
    }
}

if (-not $healthy) {
    Write-Error "LocalStack did not become healthy in time. Exiting."
    exit 1
}
Write-Host "LocalStack S3 is ready!" -ForegroundColor Green

# 4. Wait for PostgreSQL to be ready
Write-Host "Waiting for PostgreSQL to start..."
$pgReady = $false
$retryCount = 0

while (-not $pgReady -and $retryCount -lt $maxRetries) {
    $connection = New-Object System.Net.Sockets.TcpClient
    try {
        $connection.Connect("127.0.0.1", 5433)
        if ($connection.Connected) {
            $pgReady = $true
            $connection.Close()
        }
    } catch {
        # Ignore and wait
    }
    if (-not $pgReady) {
        $retryCount++
        Start-Sleep -Seconds 2
        Write-Host "Waiting for Postgres... ($retryCount/$maxRetries)"
    }
}

if (-not $pgReady) {
    Write-Error "PostgreSQL did not start on port 5433. Exiting."
    exit 1
}
Write-Host "PostgreSQL is ready!" -ForegroundColor Green

# 5. Initialize & apply Terraform
Write-Host "Running Terraform to provision S3 buckets..."
$infraDir = Join-Path $PSScriptRoot "..\infra"

# Run terraform init
$initProcess = Start-Process -FilePath $tfPath -ArgumentList "init" -WorkingDirectory $infraDir -NoNewWindow -PassThru -Wait
if ($initProcess.ExitCode -ne 0) {
    Write-Error "Terraform init failed."
    exit 1
}

# Run terraform apply
$applyProcess = Start-Process -FilePath $tfPath -ArgumentList "apply -auto-approve" -WorkingDirectory $infraDir -NoNewWindow -PassThru -Wait
if ($applyProcess.ExitCode -ne 0) {
    Write-Error "Terraform apply failed."
    exit 1
}

Write-Host "Terraform provisioning complete." -ForegroundColor Green

# 6. Apply database DDL schema using python DDL executor
Write-Host "Applying database schema DDL..."
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$schemaSqlPath = Join-Path $projectRoot "warehouse\schema.sql"

# Make sure sqlalchemy is installed before running DDL
python -m pip install sqlalchemy psycopg2-binary --quiet

python -c "import sqlalchemy; engine = sqlalchemy.create_engine('postgresql://postgres:postgres@127.0.0.1:5433/retailflow_dw'); conn = engine.connect(); sql = open(r'$schemaSqlPath').read(); conn.execute(sqlalchemy.text(sql)); conn.commit(); print('Schema created successfully.')"

Write-Host "=== Setup completed successfully! ===" -ForegroundColor Green
