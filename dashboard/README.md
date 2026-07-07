# `dashboard/` — Web Control Center

This folder contains the complete web application that wraps the entire pipeline in a browser-based UI. It has two modes:

| Mode | What it is | How to access |
| :--- | :--- | :--- |
| **Static Demo** | A pre-populated HTML snapshot. No server, no Docker, no Java needed. | Open `static/demo.html` directly in any browser |
| **Live Dashboard** | A fully functional Flask server that controls the real pipeline, streams logs, and queries the live PostgreSQL + S3 state. | Run `python dashboard/server.py`, open `http://localhost:5050` |

---

## Files

```
dashboard/
├── server.py          ← Flask backend — REST API + pipeline orchestration
└── static/
    ├── index.html     ← Live dashboard UI (talks to server.py at :5050)
    └── demo.html      ← Static demo snapshot (standalone, no server needed)
```

---

## Static Demo — `static/demo.html`

<!-- SCREENSHOT: Drop a full-page screenshot of demo.html here -->
<!-- Save as: images/demo_dashboard.png -->
<!-- Replace this block with: ![RetailFlow Static Demo](../images/demo_dashboard.png) -->
> **Screenshot placeholder** — open `static/demo.html` in Chrome, press F12 → three-dot menu → "Capture full size screenshot", save as `../images/demo_dashboard.png` and replace this block with the image tag above.

A self-contained HTML file with **no external dependencies** beyond CDN-loaded Chart.js and Google Fonts. It contains:

- Pre-computed KPI metrics (revenue, orders, customers, units, products, avg order value)
- Channel revenue doughnut chart (POS / E-commerce / Marketplace)
- Top products by revenue bar chart
- Full `fact_orders` table — all 11 loaded records
- `dim_customer` table — all 9 customers with lifetime values
- S3 bucket layout — Bronze, Gold, and Quarantine zones
- **Quarantine Zone tab** — all 7 rejected records with their exact Pydantic error (missing field, negative quantity, invalid channel enum, etc.)
- Pre-filled terminal log showing a complete successful pipeline run
- A **"Switch to Live Pipeline →"** button that prompts the user to start `server.py` and redirects to `localhost:5050`

**When to use it:** Share this file with recruiters or reviewers who don't have Docker installed. It demonstrates exactly what the live pipeline produces.

---

## Live Dashboard — `server.py` + `static/index.html`

```bash
python dashboard/server.py
# Open: http://localhost:5050
```

<!-- SCREENSHOT: Live dashboard with pipeline running (step cards animated) -->
<!-- Save as: images/pipeline_running.png -->
> **Screenshot placeholder** — start the pipeline and screenshot while step cards are animating.
> Replace with: `![Live Pipeline Running](../images/pipeline_running.png)`

### What `server.py` does

`server.py` is a [Flask](https://flask.palletsprojects.com/) application that:

1. **Serves** `static/index.html` at `GET /`
2. **Controls the full pipeline** — one button click in the UI triggers an entire infrastructure boot + 4-step ETL run in a background thread
3. **Streams live logs** — the frontend polls `/api/pipeline_status` every second and renders each log line into the terminal widget
4. **Queries live data** — after a run completes, the UI calls the analytics API endpoints to populate KPIs, charts, and tables from the real PostgreSQL warehouse

### Infrastructure bootstrap logic

When you click **▶ Start Pipeline**, `server.py` does the following **before** running the ETL steps:

```
1. Check if Docker daemon is responsive
   └── If not, attempt to launch Docker Desktop automatically
2. docker compose up -d
   └── Boots LocalStack S3 + PostgreSQL
3. Wait for port 4566 (LocalStack) to be reachable
4. Wait for port 5433 (PostgreSQL) to accept connections
5. terraform init + terraform apply
   └── Provisions S3 buckets
6. Apply warehouse/schema.sql
   └── Creates dim/fact tables
7. ── Infrastructure ready ──
8. Run ETL pipeline (4 steps via run_pipeline.ps1)
```

This means the dashboard is a **one-click setup** — you don't need to run `setup.ps1` separately.

### REST API endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/run_pipeline` | Start a pipeline run for a given `target_date` |
| `POST` | `/api/stop_pipeline` | Signal the running pipeline to stop |
| `POST` | `/api/reset` | Truncate all warehouse tables + clear all S3 objects |
| `GET` | `/api/pipeline_status` | Current pipeline state, step statuses, and last 150 log lines |
| `GET` | `/api/kpis` | Aggregate metrics from `fact_orders` |
| `GET` | `/api/revenue_by_channel` | Revenue grouped by `channel` |
| `GET` | `/api/top_skus` | Top 10 SKUs by revenue |
| `GET` | `/api/orders` | All rows from `fact_orders` |
| `GET` | `/api/customers` | All `dim_customer` rows with order count + lifetime value |
| `GET` | `/api/s3_status` | File listing for Raw, Curated, and Quarantine S3 prefixes |
| `GET` | `/api/pipeline_health` | Health check — Postgres reachable? S3 buckets exist? |

### Pipeline state machine

The backend tracks each pipeline step with a status:

```
idle → running → completed
              ↘ error
              ↘ stopped
```

The frontend polls `/api/pipeline_status` every second and animates the step cards in `index.html` accordingly — pulsing yellow while running, solid green on completion, red on error.

---

## How the demo and live versions differ

| Feature | `demo.html` (static) | `index.html` (live) |
| :--- | :--- | :--- |
| Requires Docker | No | Yes |
| Requires Python | No | Yes |
| Requires Java | No | Yes |
| Can trigger real pipeline | No | Yes |
| Data is real | Pre-baked from a real run | Queried live from PostgreSQL |
| Charts | Static data | Live from `/api/revenue_by_channel` + `/api/top_skus` |
| Terminal logs | Pre-written | Real-time streamed from running subprocess |
| Upload custom data | No | Drop files in `data/sample_orders/` and re-run |

---

## What this folder does NOT contain

- It does not run PySpark directly — it delegates to `scripts/run_pipeline.ps1`.
- It does not contain the warehouse schema — that is [`warehouse/schema.sql`](../warehouse/README.md).
- It does not contain Terraform config — that is [`infra/`](../infra/README.md).

---

## Related links

- [Flask documentation](https://flask.palletsprojects.com/)
- [Flask-CORS](https://flask-cors.readthedocs.io/)
- [Chart.js documentation](https://www.chartjs.org/docs/latest/)
- [boto3 S3 client](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html)
- [psycopg2 documentation](https://www.psycopg.org/docs/)

---

*Back to [project root](../Readme.md)*
