# `ingestion/` — Raw Data Ingestion (Bronze Layer)

This is the **first step** of the pipeline. It takes the raw source files from your local disk and uploads them into the S3 data lake, creating the Bronze layer — the untouched, unprocessed copy of exactly what the source systems sent.

---

## Files

| File | Purpose |
| :--- | :--- |
| `upload_to_lake.py` | Reads raw CSV and JSON files from `data/sample_orders/`, uploads them to LocalStack S3 under a dated partition |

---

## What "Bronze layer" means

The [Medallion Architecture](https://www.databricks.com/glossary/medallion-architecture) (Bronze / Silver / Gold) is a standard lakehouse design pattern:

| Layer | What it stores | Location in this project |
| :--- | :--- | :--- |
| **Bronze** | Raw files, exactly as received from the source | `s3://retailflow-raw/raw/orders/YYYY-MM-DD/` |
| **Silver** | Validated, clean records (after Pydantic check) | `s3://retailflow-raw/validated/orders/YYYY-MM-DD/` |
| **Gold** | Deduplicated, aggregated Parquet (after PySpark) | `s3://retailflow-curated/curated/orders/processed_date=YYYY-MM-DD/` |

This script only handles the **Bronze** upload — it does not validate, transform, or interpret the files in any way.

---

## What it does — step by step

```
data/sample_orders/
  ├── pos_export_2026-07-01.csv
  └── ecommerce_export_2026-07-01.json
          │
          │  boto3 s3.upload_file()
          ▼
s3://retailflow-raw/
  └── raw/
      └── orders/
          └── 2026-07-01/
              ├── pos_export_2026-07-01.csv
              └── ecommerce_export_2026-07-01.json
```

The target partition path is built from the `target_date` argument, so each day's data lands in its own folder — a standard **date partitioning** strategy that enables efficient range scans and partition pruning.

---

## Key implementation details

**Uses boto3 with the LocalStack endpoint:**

```python
s3 = boto3.client(
    "s3",
    endpoint_url="http://localhost:4566",   # LocalStack, not real AWS
    aws_access_key_id="mock",
    aws_secret_access_key="mock",
    region_name="us-east-1"
)
```

Swapping to real AWS S3 requires only removing the `endpoint_url` line and providing real credentials. Everything else — the bucket names, key paths, and `upload_file()` calls — remains identical.

**S3 key naming convention:**

```
raw/orders/{target_date}/pos_export_{target_date}.csv
raw/orders/{target_date}/ecommerce_export_{target_date}.json
```

This is a Hive-compatible partition path format, which makes the data immediately compatible with tools like [AWS Athena](https://aws.amazon.com/athena/), [AWS Glue](https://aws.amazon.com/glue/), and [Apache Spark](https://spark.apache.org/).

---

## How to run standalone

```bash
# Upload files for a specific date (LocalStack must be running)
python ingestion/upload_to_lake.py 2026-07-01
```

Expected output:
```
Uploading .../pos_export_2026-07-01.csv to s3://retailflow-raw/raw/orders/2026-07-01/...
CSV upload successful.
Uploading .../ecommerce_export_2026-07-01.json to s3://retailflow-raw/raw/orders/2026-07-01/...
JSON upload successful.
All files ingested successfully for date 2026-07-01
```

---

## Verify the upload

After running, confirm the files landed in S3:

```bash
aws --endpoint-url=http://localhost:4566 s3 ls s3://retailflow-raw/raw/ --recursive
```

---

## Why store raw files before validating?

1. **Data lineage** — you always have the original unmodified file. If a bug is discovered in the validation logic months later, you can replay the entire pipeline from Bronze without re-requesting data from the source system.
2. **Audit trail** — regulators and compliance teams often require that raw inputs be preserved exactly as received.
3. **Debugging** — if a validated record looks wrong, you can diff it against the raw Bronze file to see what the validator did.

This "immutable raw storage" approach is a core principle of the [Lakehouse architecture](https://www.databricks.com/blog/2020/01/30/what-is-a-data-lakehouse.html) pioneered by Databricks.

---

## What this folder does NOT contain

- It does not validate records — that is [`validators/`](../validators/README.md).
- It does not read from S3 — it only writes to it.
- It does not handle streaming ingestion — this is a batch pipeline (file-based, date-partitioned).

---

## Related links

- [boto3 S3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html)
- [boto3 upload_file](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/upload_file.html)
- [Medallion Architecture — Databricks](https://www.databricks.com/glossary/medallion-architecture)
- [LocalStack S3 docs](https://docs.localstack.cloud/user-guide/aws/s3/)

---

*Back to [project root](../Readme.md)*
