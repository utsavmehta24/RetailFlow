# `data/` — Raw Sample Transaction Files

This folder contains the raw input data files that the pipeline ingests. They simulate what a real retail business would receive from two separate source systems on a given trading day.

---

## Folder structure

```
data/
└── sample_orders/
    ├── pos_export_2026-07-01.csv        ← Physical POS terminal export
    └── ecommerce_export_2026-07-01.json ← E-commerce storefront export
```

The filename convention is `<source>_export_<YYYY-MM-DD>.<ext>`. The date in the filename is the **partition date** — it tells the pipeline which S3 prefix to use when uploading to the Bronze layer.

---

## File 1 — `pos_export_2026-07-01.csv`

Simulates a nightly CSV dump from a physical Point-of-Sale (POS) terminal system (e.g. Square, Lightspeed).

**Schema:**

| Column | Type | Description |
| :--- | :--- | :--- |
| `order_id` | string | Unique order identifier, prefix `POS-` |
| `customer_id` | string | Customer reference ID, prefix `CUST-` |
| `order_date` | date (YYYY-MM-DD) | Date the transaction occurred |
| `sku` | string | Product stock-keeping unit, prefix `PROD-` |
| `quantity` | integer | Number of units purchased (must be > 0) |
| `unit_price` | float | Price per unit in local currency (must be > 0) |
| `channel` | enum | Must be one of: `pos`, `ecommerce`, `marketplace` |

**Sample rows:**

```csv
order_id,customer_id,order_date,sku,quantity,unit_price,channel
POS-1001,CUST-001,2026-07-01,PROD-101,2,15.50,pos
POS-1002,CUST-002,2026-07-01,PROD-102,1,8.99,pos
```

**Intentional bad records (for quarantine testing):**

| Row | Problem | Field | Bad value |
| :--- | :--- | :--- | :--- |
| POS-1005 | Missing required field | `order_date` | `""` (empty) |
| POS-1006 | Negative quantity | `quantity` | `-3` |
| POS-1007 | Negative price | `unit_price` | `-5.00` |
| POS-1008 | Invalid channel enum | `channel` | `"invalid_channel"` |
| POS-1001 (last row) | Duplicate record | entire row | Exact copy of first row — tests deduplication in PySpark |

---

## File 2 — `ecommerce_export_2026-07-01.json`

Simulates a nightly JSON export from an e-commerce storefront (e.g. Shopify, WooCommerce).

**Schema:** Same fields as the CSV, delivered as a JSON array of objects.

```json
[
  {
    "order_id": "ECOMM-2001",
    "customer_id": "CUST-101",
    "order_date": "2026-07-01",
    "sku": "PROD-201",
    "quantity": 1,
    "unit_price": 120.00,
    "channel": "ecommerce"
  }
]
```

**Intentional bad records:**

| Row | Problem | Field | Bad value |
| :--- | :--- | :--- | :--- |
| ECOMM-2004 | Zero quantity (not positive) | `quantity` | `0` |
| ECOMM-2005 | Negative price | `unit_price` | `-1.99` |
| ECOMM-2006 | Empty customer ID | `customer_id` | `""` |

---

## Why bad records are intentional

Real production data is never perfectly clean. The bad records in these files are **deliberately designed** to exercise every validation rule in [`validators/order_schema.py`](../validators/README.md):

- Missing required fields
- Type constraint violations (positive integer, positive float)
- Enum violations (invalid channel name)
- Duplicate records (tests PySpark deduplication logic)

After validation, you can inspect exactly which records were rejected and why in the Quarantine Zone tab of the dashboard, or by querying S3 directly:

```bash
aws --endpoint-url=http://localhost:4566 s3 cp \
  s3://retailflow-raw/quarantine/orders/2026-07-01/quarantined_orders.jsonl - | head -20
```

---

## Using your own data

Drop your own `.csv` or `.json` files into `data/sample_orders/` following the same schema above. Then:

1. Click **🧹 Reset** in the dashboard to clear the warehouse and S3 buckets
2. Click **▶ Start Pipeline** — the pipeline picks up whatever files are in this folder
3. Watch the KPIs, charts, and tables update with your data

The file date in the filename should match the **Target Ingestion Date** you set in the dashboard control panel.

---

## What this folder does NOT contain

- It does not contain processed or transformed data — those live in S3 (LocalStack) after a pipeline run.
- It does not contain production customer data — all names and IDs are synthetic test fixtures.
- It does not auto-generate new sample files — the same files are reused across runs (idempotent design).

---

*Back to [project root](../Readme.md)*
