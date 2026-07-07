# `scripts/` — Pipeline Orchestration Scripts

This folder contains the shell scripts that tie every component of the project together. They are the entry point for setting up the environment, running the full ETL pipeline, and tearing everything down cleanly — on both Windows and Linux/macOS.

---

## Files

| File | Platform | What it does |
| :--- | :--- | :--- |
| `setup.ps1` | Windows (PowerShell) | Boots Docker, downloads Terraform, waits for services, applies IaC, applies DB schema |
| `setup.sh` | Linux / macOS (Bash) | Same as above for Unix systems |
| `run_pipeline.ps1` | Windows (PowerShell) | Runs all 4 ETL steps for a target date |
| `run_pipeline.sh` | Linux / macOS (Bash) | Same as above for Unix systems |
| `teardown.ps1` | Windows (PowerShell) | Destroys Terraform resources, stops Docker containers + volumes |
| `teardown.sh` | Linux / macOS (Bash) | Same as above for Unix systems |

---

## `setup.ps1` / `setup.sh` — Environment Bootstrap

Run this **once** before the first pipeline execution. It:

1. **Starts Docker containers** — runs `docker compose up -d` to boot LocalStack S3 (port 4566) and PostgreSQL (port 5433)
2. **Downloads Terraform** — if `bin/terraform.exe` is absent, fetches v1.9.2 from HashiCorp's release page and extracts it into `bin/`
3. **Waits for LocalStack** — polls `http://127.0.0.1:4566` every 2 seconds (up to 60 seconds) before proceeding
4. **Waits for PostgreSQL** — attempts a TCP connection to port 5433 (up to 60 seconds)
5. **Runs `terraform init` + `terraform apply`** — provisions the two S3 buckets (`retailflow-raw`, `retailflow-curated`) inside LocalStack
6. **Applies `warehouse/schema.sql`** — creates the `dim_customer`, `dim_product`, `dim_date`, `fact_orders` tables in PostgreSQL

**Windows:**
```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

**Linux / macOS:**
```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

Expected output:
```
=== Starting RetailFlow Environment Setup ===
Spinning up Docker containers (LocalStack & Postgres)...
LocalStack S3 is ready!
PostgreSQL is ready!
Terraform provisioning complete.
=== Setup completed successfully! ===
```

---

## `run_pipeline.ps1` / `run_pipeline.sh` — ETL Pipeline Runner

Executes the full four-step ETL pipeline for a given date. Call this after setup is complete.

**Parameters:**

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `-TargetDate` (PS) / `$1` (Bash) | `2026-07-01` | The partition date to process |

**Windows:**
```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_pipeline.ps1 -TargetDate 2026-07-01
```

**Linux / macOS:**
```bash
./scripts/run_pipeline.sh 2026-07-01
```

### What it does internally

Before calling each Python module, the script sets critical environment variables:

```powershell
$env:PYSPARK_PYTHON       = "python"
$env:PYSPARK_DRIVER_PYTHON = "python"
$env:AWS_ENDPOINT_URL     = "http://127.0.0.1:4566"    # forces LocalStack
$env:DATABASE_URL         = "postgresql://postgres:postgres@127.0.0.1:5433/retailflow_dw"
$env:JAVA_HOME            = "<auto-detected from PATH>"
$env:HADOOP_HOME          = "<project_root>/hadoop"    # Windows only
```

It then calls each step in sequence, **failing fast** if any step exits non-zero:

```
Step 1/4  python ingestion/upload_to_lake.py      2026-07-01
Step 2/4  python validators/order_schema.py       2026-07-01
Step 3/4  python spark_jobs/transform_orders.py   2026-07-01
Step 4/4  python warehouse/load_to_postgres.py    2026-07-01
```

### Windows-specific: JAVA_HOME auto-detection

PySpark requires `JAVA_HOME` to be set. The script dynamically resolves the Java installation path at runtime:

```powershell
$javaPath = (Get-Command java -ErrorAction Stop).Source
$env:JAVA_HOME = Split-Path (Split-Path $javaPath -Parent) -Parent
```

This handles cases where `JAVA_HOME` is stale in the registry but Java is correctly on `PATH`.

### Windows-specific: Hadoop winutils auto-download

If `hadoop/bin/winutils.exe` or `hadoop/bin/hadoop.dll` are missing, the script downloads them automatically from the [cdarlint/winutils](https://github.com/cdarlint/winutils) repository before launching PySpark. See [`hadoop/README.md`](../hadoop/README.md) for details.

---

## `teardown.ps1` / `teardown.sh` — Clean Shutdown

Destroys everything in the reverse order of setup:

1. **`terraform destroy`** — removes the S3 buckets from LocalStack (all data inside is deleted)
2. **`docker compose down -v`** — stops and removes the containers **and their named volumes** (all PostgreSQL data is wiped)

**Windows:**
```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\teardown.ps1
```

**Linux / macOS:**
```bash
./scripts/teardown.sh
```

> **Warning:** Teardown is destructive and irreversible. It deletes all data in the LocalStack S3 buckets and the PostgreSQL database. Only run this when you are done and want a clean slate.

---

## Typical workflow

```
First time:
  1. setup.ps1              ← boot infrastructure
  2. run_pipeline.ps1       ← load data for 2026-07-01

Subsequent runs (infrastructure already running):
  3. run_pipeline.ps1 -TargetDate 2026-07-02   ← load a second day

When done:
  4. teardown.ps1           ← destroy everything
```

Or skip all of this and use the dashboard (`python dashboard/server.py`) which runs setup and the pipeline automatically with a single button click — see [`dashboard/README.md`](../dashboard/README.md).

---

## What these scripts do NOT do

- They do not install Python packages — run `pip install -r requirements.txt` separately first.
- They do not install Docker or Java — those must be pre-installed.
- They do not deploy to real AWS — the endpoint is always `http://127.0.0.1:4566` (LocalStack).

---

*Back to [project root](../Readme.md)*
