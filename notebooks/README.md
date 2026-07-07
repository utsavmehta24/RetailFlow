# `notebooks/` — Exploratory Analysis & Business Intelligence

This folder contains [Jupyter Notebooks](https://jupyter.org/) for interactive data exploration and business intelligence analysis on top of the loaded PostgreSQL data warehouse. Notebooks are the final consumer layer — sitting above the Star Schema and treating it as a ready-made analytics database.

---

## Files

| File | Purpose |
| :--- | :--- |
| `analysis.ipynb` | EDA + BI analysis on `fact_orders`, `dim_customer`, `dim_product`, `dim_date` |

---

## What `analysis.ipynb` covers

The notebook connects directly to the PostgreSQL warehouse and runs analytical queries to produce charts and insights that a business analyst or product manager would care about:

- **Revenue by channel** — how much came from POS vs E-commerce vs Marketplace
- **Top products by revenue and units sold** — which SKUs are driving the business
- **Customer segments** — Premium vs Standard customer spend patterns
- **Time-series analysis** — revenue trends by date, day-of-week effects
- **Order size distribution** — average order value, multi-item vs single-item orders
- **Quarantine analysis** — what types of data quality errors are most common

These analyses use [Pandas](https://pandas.pydata.org/), [Matplotlib](https://matplotlib.org/), and [Plotly](https://plotly.com/python/) for interactive visualisations.

---

## How to run

### Prerequisites

Make sure the pipeline has run at least once so there is data in the warehouse:

```bash
# 1. Install dependencies (if not already done)
pip install -r requirements.txt

# 2. Start Jupyter
jupyter notebook notebooks/analysis.ipynb
```

Or open JupyterLab for a more modern interface:

```bash
jupyter lab
```

Then navigate to `notebooks/analysis.ipynb` in the file browser.

### Database connection

The notebook connects to the same PostgreSQL instance used by the pipeline:

```python
import sqlalchemy
engine = sqlalchemy.create_engine(
    "postgresql://postgres:postgres@localhost:5433/retailflow_dw"
)
```

PostgreSQL must be running (either started via `setup.ps1` or `docker compose up -d`) before running notebook cells.

---

## Example queries you can run inside the notebook

```python
import pandas as pd
import sqlalchemy

engine = sqlalchemy.create_engine("postgresql://postgres:postgres@localhost:5433/retailflow_dw")

# Revenue by channel
df_channel = pd.read_sql("""
    SELECT channel,
           SUM(line_total)  AS revenue,
           COUNT(*)          AS orders,
           AVG(unit_price)   AS avg_unit_price
    FROM fact_orders
    GROUP BY channel
    ORDER BY revenue DESC
""", engine)

# Top 10 products
df_products = pd.read_sql("""
    SELECT p.product_name, p.category,
           SUM(f.quantity)   AS units_sold,
           SUM(f.line_total) AS revenue
    FROM fact_orders f
    JOIN dim_product p ON f.sku = p.sku
    GROUP BY p.product_name, p.category
    ORDER BY revenue DESC
    LIMIT 10
""", engine)

# Customer lifetime value distribution
df_clv = pd.read_sql("""
    SELECT c.customer_name, c.segment,
           COUNT(f.order_id)  AS total_orders,
           SUM(f.line_total)  AS lifetime_value
    FROM dim_customer c
    LEFT JOIN fact_orders f ON c.customer_id = f.customer_id
    GROUP BY c.customer_name, c.segment
    ORDER BY lifetime_value DESC
""", engine)
```

---

## Difference between the notebook and the dashboard

| | `analysis.ipynb` | `dashboard/static/index.html` |
| :--- | :--- | :--- |
| **Audience** | Data analyst / engineer | Business stakeholder / recruiter |
| **Interface** | Jupyter cell-by-cell | Live web dashboard |
| **Customisation** | Full — write any SQL | Fixed — predefined charts |
| **Charts** | Matplotlib / Plotly (interactive) | Chart.js |
| **Use case** | Deep-dive analysis, ad-hoc queries | Pipeline monitoring, KPI overview |

Use the notebook when you want to dig deeper than the dashboard allows — segmenting customers, plotting distributions, testing hypotheses.

---

## What this folder does NOT contain

- It does not run the ETL pipeline — that is [`scripts/`](../scripts/README.md).
- It does not define the warehouse schema — that is [`warehouse/`](../warehouse/README.md).
- It does not replace the dashboard — both serve different audiences.

---

## Related links

- [Jupyter documentation](https://docs.jupyter.org/)
- [JupyterLab](https://jupyterlab.readthedocs.io/)
- [Pandas read_sql](https://pandas.pydata.org/docs/reference/api/pandas.read_sql.html)
- [Plotly Python](https://plotly.com/python/)
- [Matplotlib](https://matplotlib.org/stable/index.html)
- [SQLAlchemy](https://docs.sqlalchemy.org/en/20/)

---

*Back to [project root](../Readme.md)*
