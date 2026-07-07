# RetailFlow — Local Data Lake → Data Warehouse Pipeline

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![PySpark](https://img.shields.io/badge/PySpark-3.5-orange?logo=apachespark&logoColor=white)](https://spark.apache.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Terraform](https://img.shields.io/badge/Terraform-1.9-purple?logo=terraform&logoColor=white)](https://www.terraform.io/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![LocalStack](https://img.shields.io/badge/LocalStack-S3-black?logo=amazon-aws&logoColor=white)](https://localstack.cloud/)

> **A production-grade batch data engineering pipeline** that ingests multi-source retail transactions, validates schemas with Pydantic, transforms data with PySpark, lands everything in a Lakehouse on local S3, and populates a PostgreSQL Star Schema Data Warehouse — running at **zero cloud cost** inside Docker.

---

## 👀 Just want to see it? No setup required.

The dashboard is available as a fully preloaded static snapshot — real pipeline output, charts, tables, and S3 bucket layout already populated from a real run.

→ **[Open the Static Demo](dashboard/static/demo.html)** *(open directly in your browser — no Docker, no Java, no server)*

<!-- SCREENSHOT: Drop your dashboard hero screenshot here -->
<!-- Suggested filename: images/demo_dashboard.png -->
<!-- To take a screenshot: open dashboard/static/demo.html in Chrome, press F12 > ... > Capture full size screenshot -->
> **Screenshot placeholder** — open `dashboard/static/demo.html` in your browser and take a full-page screenshot, then save it as `images/demo_dashboard.png` and replace this block with:
> `![RetailFlow Dashboard](images/demo_dashboard.png)`

**Want to run the actual pipeline?** Jump to [Running the Live Pipeline](#-running-the-live-pipeline).

---

## What Problem Does This Solve?

Real retail businesses get data from multiple disconnected systems — a physical POS terminal exporting CSV, an e-commerce platform exporting JSON — each with inconsistent schemas and dirty data. This pipeline:

1. **Ingests** both formats into a raw data lake (Bronze layer)
2. **Validates** every record with strict type enforcement, routing rejects to a quarantine zone instead of crashing
3. **Transforms** clean data with PySpark into deduplicated, aggregate-enriched Parquet (Gold layer)
4. **Loads** into a Star Schema warehouse ready for BI queries

Everything runs from a single web dashboard with real-time log streaming and step-by-step progress tracking.

---

## Dashboard Preview

<!-- SCREENSHOT: Pipeline step cards in "running" state -->
<!-- Suggested filename: images/pipeline_steps.png -->
<!-- Capture while pipeline is running to show the animated step cards -->
> **Screenshot placeholder** — run the live pipeline at `http://localhost:5050` and screenshot the step cards while running.
> Replace this block with: `![Pipeline Steps](images/pipeline_steps.png)`

<!-- SCREENSHOT: KPI metrics and charts after a completed run -->
<!-- Suggested filename: images/kpi_charts.png -->
> **Screenshot placeholder** — after a completed run, screenshot the KPI row + channel/SKU charts.
> Replace this block with: `![KPI Charts](images/kpi_charts.png)`

<!-- SCREENSHOT: fact_orders table tab -->
<!-- Suggested filename: images/orders_table.png -->
> **Screenshot placeholder** — screenshot the Orders (fact_orders) tab.
> Replace this block with: `![Orders Table](images/orders_table.png)`

---

## Tech Stack

| Layer | Technology | What it replaces in production |
| :--- | :--- | :--- |
| Containerization | [Docker Compose](https://docs.docker.com/compose/) | AWS ECS / EC2 |
| Object Storage | [LocalStack S3](https://localstack.cloud/) | [AWS S3](https://aws.amazon.com/s3/) |
| Infrastructure as Code | [Terraform](https://www.terraform.io/) | AWS IAM + Resource Provisioner |
| Schema Validation | [Pydantic v2](https://docs.pydantic.dev/latest/) | AWS Lambda data quality check |
| Transformation Engine | [PySpark 3.5](https://spark.apache.org/docs/latest/api/python/) | [AWS Glue](https://aws.amazon.com/glue/) / [Amazon EMR](https://aws.amazon.com/emr/) |
| Data Warehouse | [PostgreSQL 16](https://www.postgresql.org/docs/16/) | [Amazon RDS](https://aws.amazon.com/rds/) / [Redshift](https://aws.amazon.com/redshift/) |
| Dashboard Backend | [Flask](https://flask.palletsprojects.com/) + [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) | REST API layer |
| Dashboard Frontend | Vanilla JS + [Chart.js](https://www.chartjs.org/) | BI tool (Tableau / Power BI) |

---

## Architecture

```
  ┌──────────────────────────────────────────────────────────┐
  │                    Raw Data Sources                       │
  │  pos_export_YYYY-MM-DD.csv      ecommerce_YYYY-MM-DD.json│
  │  (Physical POS Terminal)        (E-commerce Storefront)   │
  └──────────────────┬──────────────────────────────┬────────┘
                     │           boto3 upload        │
                     └──────────────┬───────────────┘
                                    ▼
                 ┌──────────────────────────────────┐
                 │       S3 Bronze Layer             │
                 │  retailflow-raw/raw/orders/       │
                 │  YYYY-MM-DD/pos.csv               │
                 │  YYYY-MM-DD/ecommerce.json        │
                 └────────────────┬─────────────────┘
                                  │  Pydantic v2 validation
                                  ▼
                 ┌──────────────────────────────────┐
                 │       Validation Layer            │
                 │  ✅ Valid   →  Silver Layer S3    │
                 │  ❌ Invalid →  Quarantine Zone S3 │
                 │  (type, +quantity, +price,        │
                 │   channel enum, required fields)  │
                 └────────────────┬─────────────────┘
                                  │  PySpark SparkSession
                                  ▼
                 ┌──────────────────────────────────┐
                 │       S3 Gold Layer (Parquet)     │
                 │  Deduplicated + Aggregated        │
                 │  retailflow-curated/curated/      │
                 └────────────────┬─────────────────┘
                                  │  psycopg2 + pandas
                                  ▼
                 ┌──────────────────────────────────┐
                 │    PostgreSQL Data Warehouse      │
                 │         Star Schema               │
                 │                                   │
                 │  dim_customer    dim_product       │
                 │        ↘              ↙           │
                 │           fact_orders              │
                 │        ↗              ↖           │
                 │    dim_date       (channel, SKU)  │
                 └────────────────┬─────────────────┘
                                  │
                                  ▼
                 ┌──────────────────────────────────┐
                 │    RetailFlow Web Dashboard       │
                 │    Flask API  +  Chart.js UI      │
                 │    http://localhost:5050          │
                 └──────────────────────────────────┘
```

---

## Project Structure

```
retailflow/
│
├── 📄 Readme.md                  ← You are here (master README)
├── 📄 docker-compose.yml         ← LocalStack S3 + PostgreSQL containers
├── 📄 requirements.txt           ← All Python dependencies
│
├── 📁 bin/                       ← Local Terraform binary (auto-downloaded)
│   └── README.md
│
├── 📁 hadoop/                    ← Windows PySpark compatibility binaries
│   └── README.md
│
├── 📁 data/                      ← Raw sample transaction files
│   └── README.md
│
├── 📁 validators/                ← Pydantic schema + quarantine router
│   └── README.md
│
├── 📁 ingestion/                 ← boto3 S3 uploader (Bronze layer)
│   └── README.md
│
├── 📁 spark_jobs/                ← PySpark ETL transform (Gold/Parquet)
│   └── README.md
│
├── 📁 warehouse/                 ← Star Schema DDL + Postgres loader
│   └── README.md
│
├── 📁 infra/                     ← Terraform IaC for S3 buckets
│   └── README.md
│
├── 📁 scripts/                   ← Setup / run / teardown orchestration
│   └── README.md
│
├── 📁 dashboard/                 ← Flask API + live control center UI
│   └── README.md
│
├── 📁 notebooks/                 ← Jupyter EDA and BI analysis
│   └── README.md
│
└── 📁 images/                    ← Screenshots for this README
```

---

## Key Engineering Decisions

**Why quarantine instead of fail?**
Production pipelines never crash on bad data — they isolate it. The [Pydantic](https://docs.pydantic.dev/latest/) validation layer catches type mismatches, negative prices, missing required fields, and invalid channel enums. Each bad record is written to `s3://retailflow-raw/quarantine/` with its full error payload for downstream alerting and re-processing. This is the same pattern used at companies like Airbnb and Uber for their data lakehouse architectures.

**Why Parquet for the Gold layer?**
[Apache Parquet](https://parquet.apache.org/) is a columnar format — it compresses repetitive categorical fields (channel, SKU, customer_id) by 60–80% versus CSV, and analytical queries that scan only a few columns skip entire row groups. This is why [AWS Glue](https://aws.amazon.com/glue/) and [Redshift Spectrum](https://docs.aws.amazon.com/redshift/latest/dg/c-using-spectrum.html) use it as default.

**Why a Star Schema instead of a flat table?**
The [Star Schema](https://en.wikipedia.org/wiki/Star_schema) separates slowly-changing descriptors (customer names, product categories) from high-volume transaction facts. Dimension tables are small and cacheable; the fact table is append-only and partitionable. [Tableau](https://www.tableau.com/), [Power BI](https://powerbi.microsoft.com/), and [Looker](https://looker.com/) expect exactly this layout for performant dashboards.

**Why LocalStack + Terraform instead of mocking?**
[boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html), PySpark's S3A connector, and Terraform all hit the actual [S3 HTTP API](https://docs.aws.amazon.com/AmazonS3/latest/API/Welcome.html). Swapping to real AWS is a one-line endpoint change — no mock library shims, no fake adapters. [LocalStack](https://localstack.cloud/) is the industry standard for local cloud development.

---

## Running the Live Pipeline

### Prerequisites

| Requirement | Version | Link |
| :--- | :--- | :--- |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Latest | Required for LocalStack + PostgreSQL |
| [Python](https://www.python.org/downloads/) | 3.11+ | Pipeline runtime |
| [Java JDK](https://adoptium.net/) | 17 or 21 | Required by PySpark's JVM |

```bash
# Install all Python dependencies
pip install -r requirements.txt
```

### Step 1 — Boot Infrastructure

Starts Docker containers (LocalStack + PostgreSQL), applies Terraform S3 config, and initialises the database schema.

**Windows (PowerShell):**
```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

**Linux / macOS:**
```bash
./scripts/setup.sh
```

### Step 2 — Launch the Dashboard

```bash
python dashboard/server.py
```

Open **[http://localhost:5050](http://localhost:5050)** — click **▶ Start Pipeline**. The dashboard boots Docker, runs Terraform, executes all 4 ETL steps, and populates the analytics views without a single extra command.

### Step 3 — Or run via CLI

```powershell
# Windows
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_pipeline.ps1 -TargetDate 2026-07-01
```
```bash
# Linux / macOS
./scripts/run_pipeline.sh 2026-07-01
```

### Step 4 — Tear Down

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\teardown.ps1   # Windows
./scripts/teardown.sh                                                   # Linux / macOS
```

---

## What a Successful Run Looks Like

```
=== Running RetailFlow Pipeline for date: 2026-07-01 ===

[Step 1/4] Ingesting raw POS & E-commerce exports...
  Uploaded pos_export_2026-07-01.csv     → s3://retailflow-raw/raw/orders/2026-07-01/
  Uploaded ecommerce_export_2026-07-01.json → s3://retailflow-raw/raw/orders/2026-07-01/

[Step 2/4] Validating records and routing to quarantine...
  Validation complete. Valid: 11, Quarantined: 7
  Valid records   → s3://retailflow-raw/validated/orders/2026-07-01/valid_orders.csv
  Bad records     → s3://retailflow-raw/quarantine/orders/2026-07-01/quarantined_orders.jsonl

[Step 3/4] Running PySpark transformation...
  Reading:  s3a://retailflow-raw/validated/orders/2026-07-01/
  Writing:  s3a://retailflow-curated/curated/orders/processed_date=2026-07-01
  Curated Parquet written successfully.

[Step 4/4] Loading curated Parquet to PostgreSQL...
  Inserted 9  → dim_customer
  Inserted 7  → dim_product
  Inserted 1  → dim_date
  Loaded  11  → fact_orders

=== Pipeline completed successfully for 2026-07-01! ===
```

---

## Validating Outputs Manually

### Query the Data Warehouse

```bash
# View loaded orders
docker exec -it retailflow-postgres psql -U postgres -d retailflow_dw \
  -c "SELECT order_id, customer_id, sku, channel, order_date, quantity, line_total FROM fact_orders;"

# Customer lifetime value
docker exec -it retailflow-postgres psql -U postgres -d retailflow_dw \
  -c "SELECT c.customer_id, c.customer_name, COUNT(f.order_id) AS orders, SUM(f.line_total) AS ltv
      FROM dim_customer c JOIN fact_orders f ON c.customer_id = f.customer_id
      GROUP BY c.customer_id, c.customer_name ORDER BY ltv DESC;"
```

### Inspect S3 Layers

```bash
# Bronze — raw uploads
aws --endpoint-url=http://localhost:4566 s3 ls s3://retailflow-raw/raw/ --recursive

# Silver — validated CSV
aws --endpoint-url=http://localhost:4566 s3 ls s3://retailflow-raw/validated/ --recursive

# Gold — curated Parquet
aws --endpoint-url=http://localhost:4566 s3 ls s3://retailflow-curated/curated/ --recursive

# Quarantine — rejected records
aws --endpoint-url=http://localhost:4566 s3 ls s3://retailflow-raw/quarantine/ --recursive
```

---

## Cloud Deployment Mapping

| Local Component | Production AWS Equivalent | Docs |
| :--- | :--- | :--- |
| LocalStack S3 | [AWS S3](https://aws.amazon.com/s3/) | Identical boto3/S3A API |
| PostgreSQL (Docker) | [Amazon RDS](https://aws.amazon.com/rds/) | Same JDBC driver |
| `run_pipeline.ps1` | [Apache Airflow](https://airflow.apache.org/) DAG / [AWS Step Functions](https://aws.amazon.com/step-functions/) | Replace cron with DAG |
| `upload_to_lake.py` | [AWS Kinesis Firehose](https://aws.amazon.com/kinesis/data-firehose/) → S3 | Real-time ingest |
| `order_schema.py` | [AWS Lambda](https://aws.amazon.com/lambda/) data quality fn | Serverless validation |
| `transform_orders.py` | [AWS Glue](https://aws.amazon.com/glue/) / [Amazon EMR](https://aws.amazon.com/emr/) | Managed PySpark |
| `load_to_postgres.py` | [Amazon Redshift](https://aws.amazon.com/redshift/) COPY or Glue → RDS | Column store |
| Terraform `main.tf` | [Terraform AWS provider](https://registry.terraform.io/providers/hashicorp/aws/latest) | Change endpoint, deploy |

---

## Sample Data

The pipeline ships with two intentionally realistic test files in [`data/sample_orders/`](data/):

| File | Format | Records | Bad Records |
| :--- | :--- | :--- | :--- |
| `pos_export_2026-07-01.csv` | CSV | 11 | 4 (missing date, negative qty, negative price, invalid channel) |
| `ecommerce_export_2026-07-01.json` | JSON | 8 | 3 (zero qty, negative price, empty customer_id) |

To test with your own data: drop files into `data/sample_orders/`, click **🧹 Reset** in the dashboard, then **▶ Start Pipeline**.

---

## License

This project is licensed under the **[MIT License](https://opensource.org/licenses/MIT)**.

```
MIT License

Copyright (c) 2026 RetailFlow

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

See [https://opensource.org/licenses/MIT](https://opensource.org/licenses/MIT) for the full license text.
