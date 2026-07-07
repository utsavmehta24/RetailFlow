# `validators/` — Schema Validation & Quarantine Router

This is the **data quality gate** of the pipeline. Every record that comes out of the Bronze (raw) S3 layer passes through here before it is allowed to move to the Silver layer or reach PySpark. Records that fail validation are **quarantined** — isolated into a separate S3 prefix with a full error payload — rather than crashing or silently corrupting downstream data.

---

## Files

| File | Purpose |
| :--- | :--- |
| `order_schema.py` | Pydantic v2 schema definition, per-record validation loop, S3 read/write, quarantine routing |

---

## What it does — step by step

```
S3 Bronze Layer
    └── raw/orders/YYYY-MM-DD/pos_export.csv
    └── raw/orders/YYYY-MM-DD/ecommerce_export.json
           │
           │  download + parse
           ▼
    ┌─────────────────────────────────┐
    │  validate_records()             │
    │  ┌──────────────────────────┐   │
    │  │ Pydantic OrderRecord     │   │
    │  │ - order_id: str (min 1)  │   │
    │  │ - customer_id: str       │   │
    │  │ - order_date: date       │   │
    │  │ - sku: str               │   │
    │  │ - quantity: PositiveInt  │   │
    │  │ - unit_price: float > 0  │   │
    │  │ - channel: Literal[...]  │   │
    │  └──────────────────────────┘   │
    └──────────────┬──────────────────┘
                   │
         ┌─────────┴──────────┐
         ▼                    ▼
   Valid records         Bad records
   (Silver layer)        (Quarantine)
   validated/            quarantine/
   orders/DATE/          orders/DATE/
   valid_orders.csv      quarantined_orders.jsonl
```

---

## The Pydantic schema

[Pydantic v2](https://docs.pydantic.dev/latest/) is used for schema enforcement. The `OrderRecord` model defines exactly what a valid order looks like:

```python
class OrderRecord(BaseModel):
    order_id:    str          = Field(..., min_length=1)
    customer_id: str          = Field(..., min_length=1)
    order_date:  date                                     # must be a valid date
    sku:         str          = Field(..., min_length=1)
    quantity:    PositiveInt                              # integer > 0
    unit_price:  float        = Field(..., gt=0)          # float > 0
    channel:     Literal["pos", "ecommerce", "marketplace"]
```

Every incoming record is parsed through this model. If **any field** fails, the entire record is rejected.

---

## Validation rules enforced

| Field | Rule | What gets caught |
| :--- | :--- | :--- |
| `order_id` | `min_length=1` | Empty or missing order IDs |
| `customer_id` | `min_length=1` | Empty customer references |
| `order_date` | valid `date` | Non-date strings, empty values |
| `quantity` | `PositiveInt` | Zero, negative, or non-integer quantities |
| `unit_price` | `float > 0` | Zero, negative, or non-numeric prices |
| `channel` | Literal enum | Any value not in `["pos", "ecommerce", "marketplace"]` |

---

## Quarantine format

Each rejected record is written to a `.jsonl` (JSON Lines) file. Every line is one rejected record with:
- The original raw record as received
- The full Pydantic error list (field name, error type, message)

```json
{
  "raw_record": {"order_id": "POS-1006", "quantity": "-3", ...},
  "errors": [{"loc": ["quantity"], "msg": "Input should be greater than 0", "type": "greater_than"}],
  "error_message": "1 validation error for OrderRecord\nquantity\n  Input should be greater than 0"
}
```

This means every bad record is **fully traceable** — you know exactly which field failed and why, making re-processing straightforward.

---

## How to run standalone

```bash
# Validate records for a specific date (reads from S3, writes results back to S3)
python validators/order_schema.py 2026-07-01
```

This assumes LocalStack is running and the raw files have already been uploaded (Step 1 of the pipeline).

---

## Why this matters in production

In a real data platform, skipping this layer means:
- PySpark jobs crash or produce silent `NaN` values when they encounter bad types
- Negative prices inflate revenue metrics
- Missing customer IDs break foreign key joins in the warehouse
- Bad data reaches BI dashboards and gets reported as real numbers

The quarantine pattern used here is the same approach used at companies like Airbnb ([Minerva](https://medium.com/airbnb-engineering/minerva-airbnbs-key-metric-platform-1b8254a5dd23)) and Uber ([Ubers data quality framework](https://www.uber.com/en-IN/blog/monitoring-data-quality-at-scale/)) — reject early, store the error, fix and replay.

---

## What this folder does NOT contain

- It does not transform or aggregate data — that is the job of [`spark_jobs/`](../spark_jobs/README.md).
- It does not write to the PostgreSQL warehouse — that is [`warehouse/`](../warehouse/README.md).
- It does not define the S3 bucket structure — that is [`infra/`](../infra/README.md).

---

## Related links

- [Pydantic v2 documentation](https://docs.pydantic.dev/latest/)
- [Pydantic PositiveInt](https://docs.pydantic.dev/latest/api/types/#pydantic.types.PositiveInt)
- [Pydantic Field validators](https://docs.pydantic.dev/latest/concepts/fields/)
- [JSON Lines format](https://jsonlines.org/)

---

*Back to [project root](../Readme.md)*
