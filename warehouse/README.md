# `warehouse/` — PostgreSQL Data Warehouse (Star Schema)

This is the **final destination** of the pipeline. After PySpark has produced clean, aggregated Parquet files in the Gold S3 layer, this module reads them and loads everything into a structured [Star Schema](https://en.wikipedia.org/wiki/Star_schema) PostgreSQL database — making the data immediately queryable by BI tools, dashboards, and SQL analysts.

---

## Files

| File | Purpose |
| :--- | :--- |
| `schema.sql` | DDL — creates all four tables: `dim_customer`, `dim_product`, `dim_date`, `fact_orders` |
| `load_to_postgres.py` | Reads Gold Parquet from S3 → populates dimensions → loads fact table (idempotent) |

---

## The Star Schema design

```
                    ┌──────────────────┐
                    │   dim_customer   │
                    │ ─────────────── │
                    │ customer_id (PK) │
                    │ customer_name    │
                    │ segment          │
                    └────────┬─────────┘
                             │
┌──────────────┐    ┌────────▼──────────────────────────────┐    ┌──────────────────┐
│  dim_date    │    │              fact_orders               │    │   dim_product    │
│ ──────────── │    │ ────────────────────────────────────── │    │ ──────────────── │
│ full_date(PK)│◄───│ fact_order_key (PK, serial)            │───►│ sku (PK)         │
│ date_key     │    │ order_id                               │    │ product_name     │
│ day_of_week  │    │ customer_id (FK → dim_customer)        │    │ category         │
│ day_name     │    │ sku (FK → dim_product)                 │    └──────────────────┘
│ month        │    │ order_date (FK → dim_date)             │
│ month_name   │    │ quantity                               │
│ quarter      │    │ unit_price                             │
│ year         │    │ line_total                             │
│ is_weekend   │    │ channel                                │
└──────────────┘    │ order_total_amount                     │
                    │ order_item_count                       │
                    │ created_at                             │
                    └────────────────────────────────────────┘
```

A Star Schema has one central **fact table** (transactions) surrounded by **dimension tables** (who, what, when). This layout is optimised for analytical queries: BI tools join once and then aggregate freely.

---

## Table descriptions

### `fact_orders` — the transaction hub

Each row is one line item in one order (one customer buying one SKU in one transaction). It holds all the numeric measures:

| Column | Type | Description |
| :--- | :--- | :--- |
| `fact_order_key` | SERIAL PK | Auto-incrementing surrogate key |
| `order_id` | VARCHAR | Source order identifier (from POS or ecommerce) |
| `customer_id` | FK | Links to `dim_customer` |
| `sku` | FK | Links to `dim_product` |
| `order_date` | FK | Links to `dim_date` |
| `quantity` | INT | Units purchased |
| `unit_price` | NUMERIC | Price per unit |
| `line_total` | NUMERIC | `quantity × unit_price` (computed by PySpark) |
| `channel` | VARCHAR | `pos`, `ecommerce`, or `marketplace` |
| `order_total_amount` | NUMERIC | Total value of the whole order (all SKUs combined) |
| `order_item_count` | INT | Total units across all SKUs in the order |

### `dim_customer`

| Column | Type | Description |
| :--- | :--- | :--- |
| `customer_id` | VARCHAR PK | Source customer ID |
| `customer_name` | VARCHAR | Customer display name |
| `segment` | VARCHAR | `Premium` or `Standard` (assigned synthetically in this demo) |

### `dim_product`

| Column | Type | Description |
| :--- | :--- | :--- |
| `sku` | VARCHAR PK | Stock-keeping unit code |
| `product_name` | VARCHAR | Human-readable product name |
| `category` | VARCHAR | Product category |

The product catalog mapping used in `load_to_postgres.py`:

| SKU | Product Name | Category |
| :--- | :--- | :--- |
| PROD-101 | Espresso Beans 1kg | Coffee |
| PROD-102 | Oat Milk 1L | Dairy Alternatives |
| PROD-103 | Drip Coffee Maker | Equipment |
| PROD-104 | Ceramic Coffee Mug | Accessories |
| PROD-105 | Syrup Vanilla 750ml | Ingredients |
| PROD-201 | Organic Green Tea 100g | Tea |
| PROD-202 | Electric Tea Kettle | Equipment |
| PROD-203 | Matcha Powder 50g | Tea |
| PROD-204 | Glass Teapot 750ml | Accessories |

### `dim_date`

| Column | Type | Description |
| :--- | :--- | :--- |
| `full_date` | DATE PK | The calendar date |
| `date_key` | INT | Integer key (YYYYMMDD format) for fast range scans |
| `day_of_week` | INT | 1 = Monday … 7 = Sunday |
| `day_name` | VARCHAR | e.g. `Tuesday` |
| `month` | INT | 1–12 |
| `month_name` | VARCHAR | e.g. `July` |
| `quarter` | INT | 1–4 |
| `year` | INT | e.g. `2026` |
| `is_weekend` | BOOLEAN | `true` for Saturday or Sunday |

---

## How `load_to_postgres.py` works

The loader follows a safe **upsert / skip-duplicate** strategy:

1. **Download Parquet** from `s3://retailflow-curated/curated/orders/processed_date=YYYY-MM-DD/` into a temp directory
2. **Read into Pandas** DataFrame
3. **Extract unique customers** → compare against `dim_customer` → INSERT only new ones
4. **Extract unique SKUs** → compare against `dim_product` → INSERT only new ones
5. **Extract unique dates** → compare against `dim_date` → INSERT only new ones
6. **DELETE existing facts** for the target date (idempotent — safe to re-run)
7. **Bulk INSERT** all fact rows via `pandas.to_sql()`

This means the pipeline is **idempotent** — running it twice for the same date produces the same result, no duplicates.

---

## How to run standalone

```bash
# Load warehouse for a specific date (LocalStack + Postgres must be running)
python warehouse/load_to_postgres.py 2026-07-01
```

---

## Query examples

```sql
-- Total revenue by channel
SELECT channel, SUM(line_total) AS revenue
FROM fact_orders
GROUP BY channel
ORDER BY revenue DESC;

-- Top 5 customers by lifetime value
SELECT c.customer_name, SUM(f.line_total) AS ltv
FROM fact_orders f
JOIN dim_customer c ON f.customer_id = c.customer_id
GROUP BY c.customer_name
ORDER BY ltv DESC
LIMIT 5;

-- Weekend vs weekday revenue
SELECT d.is_weekend, SUM(f.line_total) AS revenue
FROM fact_orders f
JOIN dim_date d ON f.order_date = d.full_date
GROUP BY d.is_weekend;
```

---

## What this folder does NOT contain

- It does not transform or aggregate data — that is [`spark_jobs/`](../spark_jobs/README.md).
- It does not define S3 buckets — that is [`infra/`](../infra/README.md).
- It does not serve the dashboard API — that is [`dashboard/`](../dashboard/README.md).

---

## Related links

- [Star Schema — Wikipedia](https://en.wikipedia.org/wiki/Star_schema)
- [SQLAlchemy documentation](https://docs.sqlalchemy.org/en/20/)
- [Pandas to_sql](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_sql.html)
- [psycopg2 documentation](https://www.psycopg.org/docs/)
- [PostgreSQL 16 docs](https://www.postgresql.org/docs/16/)

---

*Back to [project root](../Readme.md)*
