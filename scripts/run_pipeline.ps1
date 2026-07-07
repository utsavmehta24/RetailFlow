param(
    [string]$TargetDate = "2026-07-01"
)

Write-Host "=== Running RetailFlow Pipeline for date: $TargetDate ===" -ForegroundColor Green

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

# Set environment variables for PySpark to find Python on Windows
$env:PYSPARK_PYTHON = "python"
$env:PYSPARK_DRIVER_PYTHON = "python"

# Force IPv4 addresses to bypass slow Windows IPv6 localhost resolution gotchas
$env:AWS_ENDPOINT_URL = "http://127.0.0.1:4566"
$env:DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:5433/retailflow_dw"

# Dynamically resolve JAVA_HOME if java is in the PATH (fixes broken/stale JAVA_HOME registry keys)
try {
    $javaPath = (Get-Command java -ErrorAction Stop).Source
    if ($javaPath) {
        $javaDir = Split-Path (Split-Path $javaPath -Parent) -Parent
        $env:JAVA_HOME = $javaDir
        Write-Host "Dynamically corrected JAVA_HOME to: $env:JAVA_HOME" -ForegroundColor Gray
    }
} catch {
    # Let PySpark handle it if java is missing
}

# Dynamically bootstrap HADOOP_HOME and winutils.exe on Windows if missing
$hadoopDir = Join-Path $projectRoot "hadoop"
$hadoopBin = Join-Path $hadoopDir "bin"
$winutilsPath = Join-Path $hadoopBin "winutils.exe"
$hadoopDllPath = Join-Path $hadoopBin "hadoop.dll"

if (-not (Test-Path $winutilsPath) -or -not (Test-Path $hadoopDllPath)) {
    Write-Host "Hadoop winutils.exe or hadoop.dll not found locally. Bootstrapping Hadoop binaries for Windows..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $hadoopBin | Out-Null
    
    # Download using Python to bypass PowerShell TLS/WebClient SSL negotiation failures
    $winutilsUrl = "https://raw.githubusercontent.com/cdarlint/winutils/master/hadoop-3.2.1/bin/winutils.exe"
    Write-Host "Downloading winutils.exe..."
    python -c "import urllib.request; urllib.request.urlretrieve('$winutilsUrl', '$winutilsPath')"
    
    $hadoopDllUrl = "https://raw.githubusercontent.com/cdarlint/winutils/master/hadoop-3.2.1/bin/hadoop.dll"
    Write-Host "Downloading hadoop.dll..."
    python -c "import urllib.request; urllib.request.urlretrieve('$hadoopDllUrl', '$hadoopDllPath')"
    
    Write-Host "Hadoop binaries bootstrapped successfully under $hadoopDir" -ForegroundColor Green
}

$resolvedHadoop = Resolve-Path $hadoopDir
$env:HADOOP_HOME = $resolvedHadoop.Path
$env:Path = "$($resolvedHadoop.Path)\bin;" + $env:Path
Write-Host "HADOOP_HOME set to: $env:HADOOP_HOME" -ForegroundColor Gray


# Step 1: Upload Raw Files to S3 Lake
Write-Host "`n[Step 1/4] Ingesting raw POS & E-commerce exports..." -ForegroundColor Cyan
python (Join-Path $projectRoot "ingestion\upload_to_lake.py") $TargetDate
if ($LASTEXITCODE -ne 0) {
    Write-Error "Ingestion step failed."
    exit 1
}

# Step 2: Schema Validation (Pydantic)
Write-Host "`n[Step 2/4] Validating records and separating quarantined data..." -ForegroundColor Cyan
python (Join-Path $projectRoot "validators\order_schema.py") $TargetDate
if ($LASTEXITCODE -ne 0) {
    Write-Error "Validation step failed."
    exit 1
}

# Step 3: Spark Transformation (PySpark)
Write-Host "`n[Step 3/4] Running PySpark transformation (clean, dedupe, window aggregates)..." -ForegroundColor Cyan
python (Join-Path $projectRoot "spark_jobs\transform_orders.py") $TargetDate
if ($LASTEXITCODE -ne 0) {
    Write-Error "PySpark transformation step failed."
    exit 1
}

# Step 4: Load to Postgres Warehouse
Write-Host "`n[Step 4/4] Loading curated Parquet to PostgreSQL database..." -ForegroundColor Cyan
python (Join-Path $projectRoot "warehouse\load_to_postgres.py") $TargetDate
if ($LASTEXITCODE -ne 0) {
    Write-Error "PostgreSQL loading step failed."
    exit 1
}

Write-Host "`n=== Pipeline run completed successfully for $TargetDate! ===" -ForegroundColor Green
