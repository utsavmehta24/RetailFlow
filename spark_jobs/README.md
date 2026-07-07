# `spark_jobs/` — PySpark Transformation (Gold Layer)

This is the **compute engine** of the pipeline. After records have been validated and written to the Silver layer, PySpark reads them, applies transformations, and writes the results as columnar Parquet files into the Gold layer — the clean, enriched, analytics-ready dataset.

---

## Files

| File | Purpose |
| :--- | :--- |
| `transform_orders.py` | PySpark ETL job — reads Silver CSV, deduplicates, computes aggregates, writes Gold Parquet |

---

## What it does — step by step

```
S3 Silver Layer
  └── validated/orders/YYYY-MM-DD/valid_orders.csv
          │
          │  SparkSession.read.csv()
          ▼
  ┌──────────────────────────────┐
  │  1. dropDuplicates()         │  Remove exact duplicate (order_id, sku) pairs
  │  2. line_total column        │  quantity × unit_price (rounded to 2dp)
  │  3. order_total_amount       │  Window SUM of line_total per order_id
  │  4. order_item_count         │  Window SUM of quantity per order_id
  └──────────────────────────────┘
          │
          │  DataFrame.write.parquet()
          ▼
S3 Gold Layer
  └── curated/orders/processed_date=YYYY-MM-DD/
      └── part-00000-xxxx.snappy.parquet
```

---

## Transformations explained

### 1. Deduplication

```python
df_deduped = df.dropDuplicates(["order_id", "sku"])
```

The raw data occasionally contains duplicate rows (e.g. the POS system sends the same transaction twice due to network retries). This step ensures each `(order_id, sku)` pair appears exactly once in the output.

### 2. Line total

```python
df_with_amounts = df_deduped.withColumn(
    "line_total",
    spark_round(col("quantity") * col("unit_price"), 2)
)
```

Each line item's total spend: `quantity × unit_price`. Rounded to 2 decimal places to match currency precision.

### 3. Order-level aggregates (Window Functions)

```python
order_window = Window.partitionBy("order_id")

df_final = df_with_amounts
    .withColumn("order_total_amount", spark_round(spark_sum("line_total").over(order_window), 2))
    .withColumn("order_item_count",   spark_sum("quantity").over(order_window))
```

[Spark Window Functions](https://spark.apache.org/docs/latest/sql-ref-syntax-qry-select-window.html) partition the data by `order_id` and compute aggregates without collapsing the rows. This means every line item in a multi-SKU order carries:
- `order_total_amount` — the total value of the entire order it belongs to
- `order_item_count` — the total number of units in that order

This denormalised design is intentional — it allows the warehouse fact table to answer order-level questions (`WHERE order_id = 'X'`) without a second aggregation query.

---

## PySpark S3 configuration

The job connects to LocalStack S3 using the [Hadoop AWS S3A connector](https://hadoop.apache.org/docs/stable/hadoop-aws/tools/hadoop-aws/index.html):

```python
SparkSession.builder
    .config("spark.jars.packages", "org.apache.hadoop:hadoop-aws:3.4.2")
    .config("spark.hadoop.fs.s3a.endpoint", "http://localhost:4566")
    .config("spark.hadoop.fs.s3a.access.key", "mock")
    .config("spark.hadoop.fs.s3a.secret.key", "mock")
    .config("spark.hadoop.fs.s3a.path.style.access", "true")
    .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
```

To point this at real AWS S3, remove the `endpoint` override and replace the mock credentials with real AWS credentials. **All other Spark code remains identical.**

---

## Why Parquet for output?

[Apache Parquet](https://parquet.apache.org/) is the industry-standard columnar storage format for big data:

| Feature | Benefit |
| :--- | :--- |
| **Columnar storage** | Queries that read only 3 columns out of 10 skip the other 7 entirely |
| **Snappy compression** | Typically 60–80% smaller than equivalent CSV |
| **Schema embedded** | No need for an external schema registry — the file knows its own types |
| **Partition-aware** | The `processed_date=YYYY-MM-DD` folder name is a Hive partition key, enabling partition pruning in Athena/Glue |
| **Splittable** | Multiple Spark workers can read different `part-XXXXX.parquet` files in parallel |

---

## How to run standalone

```bash
# Run the PySpark transformation for a specific date
# (LocalStack must be running and Silver layer must already be populated)
python spark_jobs/transform_orders.py 2026-07-01
```

PySpark will print its startup logs (JVM init takes ~20-30 seconds on first run), then:
```
Initializing PySpark with S3 endpoint: http://localhost:4566
Reading validated data from: s3a://retailflow-raw/validated/orders/2026-07-01/valid_orders.csv
Writing curated Parquet to: s3a://retailflow-curated/curated/orders/processed_date=2026-07-01
Curated Parquet written successfully.
```

---

## Verify the output

```bash
# List the Parquet files written to the Gold layer
aws --endpoint-url=http://localhost:4566 s3 ls \
    s3://retailflow-curated/curated/orders/ --recursive
```

---

## What this folder does NOT contain

- It does not validate schemas — that is [`validators/`](../validators/README.md).
- It does not load data into PostgreSQL — that is [`warehouse/`](../warehouse/README.md).
- It does not configure S3 buckets — that is [`infra/`](../infra/README.md).
- It does not run a streaming job — this is batch only.

---

## Related links

- [PySpark DataFrame API](https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql/dataframe.html)
- [PySpark Window Functions](https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql/window.html)
- [Hadoop AWS S3A connector](https://hadoop.apache.org/docs/stable/hadoop-aws/tools/hadoop-aws/index.html)
- [Apache Parquet format](https://parquet.apache.org/docs/)
- [Databricks Medallion Architecture](https://www.databricks.com/glossary/medallion-architecture)

---

*Back to [project root](../Readme.md)*
