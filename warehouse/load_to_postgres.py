import os
import sys
import tempfile
import boto3
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, text

# S3 & Database config
S3_ENDPOINT = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
CURATED_BUCKET = "retailflow-curated"
DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/retailflow_dw")

# Product Catalog Mapping
PRODUCT_CATALOG = {
    "PROD-101": ("Espresso Beans 1kg", "Coffee"),
    "PROD-102": ("Oat Milk 1L", "Dairy Alternatives"),
    "PROD-103": ("Drip Coffee Maker", "Equipment"),
    "PROD-104": ("Ceramic Coffee Mug", "Accessories"),
    "PROD-105": ("Syrup Vanilla 750ml", "Ingredients"),
    "PROD-201": ("Organic Green Tea 100g", "Tea"),
    "PROD-202": ("Electric Tea Kettle", "Equipment"),
    "PROD-203": ("Matcha Powder 50g", "Tea"),
    "PROD-204": ("Glass Teapot 750ml", "Accessories"),
}

def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id="mock",
        aws_secret_access_key="mock",
        region_name="us-east-1"
    )

def download_parquet_files(s3_client, bucket: str, prefix: str, local_dir: str) -> list[str]:
    print(f"Listing files in s3://{bucket}/{prefix}")
    try:
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    except Exception as e:
        print(f"Error connecting to S3: {e}")
        raise
        
    if "Contents" not in response:
        return []
        
    local_files = []
    for obj in response["Contents"]:
        key = obj["Key"]
        if key.endswith(".parquet"):
            filename = os.path.basename(key)
            local_path = os.path.join(local_dir, filename)
            print(f"Downloading s3://{bucket}/{key} to {local_path}")
            s3_client.download_file(bucket, key, local_path)
            local_files.append(local_path)
            
    return local_files

def load_data_to_warehouse(target_date: str):
    s3 = get_s3_client()
    prefix = f"curated/orders/processed_date={target_date}/"
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Download Parquet files from S3
        parquet_files = download_parquet_files(s3, CURATED_BUCKET, prefix, temp_dir)
        if not parquet_files:
            print(f"No Parquet files found for date {target_date} in curated bucket.")
            return False
            
        print(f"Reading {len(parquet_files)} parquet files into Pandas DataFrame")
        dfs = [pd.read_parquet(f) for f in parquet_files]
        df = pd.concat(dfs, ignore_index=True)
        
    print(f"Loaded {len(df)} records from Parquet. Starting Postgres load.")
    engine = create_engine(DB_URL)
    
    # 1. Populate dim_customer
    unique_customers = df["customer_id"].unique()
    cust_rows = []
    for cid in unique_customers:
        # Assign synthetic segment
        segment = "Premium" if sum(c.isdigit() for c in cid) % 2 == 0 else "Standard"
        cust_rows.append({
            "customer_id": cid,
            "customer_name": f"Customer {cid.split('-')[-1]}",
            "segment": segment
        })
    df_cust_new = pd.DataFrame(cust_rows)
    
    # 2. Populate dim_product
    unique_skus = df["sku"].unique()
    prod_rows = []
    for sku in unique_skus:
        name, cat = PRODUCT_CATALOG.get(sku, (f"Product {sku}", "General"))
        prod_rows.append({
            "sku": sku,
            "product_name": name,
            "category": cat
        })
    df_prod_new = pd.DataFrame(prod_rows)
    
    # 3. Populate dim_date
    unique_dates = pd.to_datetime(df["order_date"].unique())
    date_rows = []
    for dt in unique_dates:
        date_rows.append({
            "full_date": dt.date(),
            "date_key": int(dt.strftime("%Y%m%d")),
            "day_of_week": dt.dayofweek + 1, # Pandas dayofweek is 0-6, SQL is 1-7
            "day_name": dt.strftime("%A"),
            "month": dt.month,
            "month_name": dt.strftime("%B"),
            "quarter": (dt.month - 1) // 3 + 1,
            "year": dt.year,
            "is_weekend": dt.dayofweek in [5, 6]
        })
    df_date_new = pd.DataFrame(date_rows)
    
    # Insert dimensions using UPSERT / IGNORE strategy
    # To keep code simple and cross-platform, we can fetch existing keys and only insert missing ones
    with engine.begin() as conn:
        # Load missing customers
        existing_custs = pd.read_sql("SELECT customer_id FROM dim_customer", conn)["customer_id"].tolist()
        df_cust_insert = df_cust_new[~df_cust_new["customer_id"].isin(existing_custs)]
        if not df_cust_insert.empty:
            df_cust_insert.to_sql("dim_customer", conn, if_exists="append", index=False)
            print(f"Inserted {len(df_cust_insert)} new customers into dim_customer.")
            
        # Load missing products
        existing_products = pd.read_sql("SELECT sku FROM dim_product", conn)["sku"].tolist()
        df_prod_insert = df_prod_new[~df_prod_new["sku"].isin(existing_products)]
        if not df_prod_insert.empty:
            df_prod_insert.to_sql("dim_product", conn, if_exists="append", index=False)
            print(f"Inserted {len(df_prod_insert)} new products into dim_product.")
            
        # Load missing dates
        existing_dates = pd.read_sql("SELECT full_date FROM dim_date", conn)["full_date"].tolist()
        existing_dates = [d.strftime("%Y-%m-%d") if isinstance(d, datetime) or hasattr(d, "strftime") else str(d) for d in existing_dates]
        df_date_insert = df_date_new[~df_date_new["full_date"].astype(str).isin(existing_dates)]
        if not df_date_insert.empty:
            df_date_insert.to_sql("dim_date", conn, if_exists="append", index=False)
            print(f"Inserted {len(df_date_insert)} new dates into dim_date.")
            
        # 4. Load fact_orders idempotently (delete existing data for target_date before load)
        print(f"Clearing existing facts for order_date = '{target_date}'")
        conn.execute(text(f"DELETE FROM fact_orders WHERE order_date = :dt"), {"dt": target_date})
        
        # Prepare fact table load dataframe matching schema columns
        df_facts = df[[
            "order_id", "customer_id", "sku", "order_date", 
            "quantity", "unit_price", "line_total", "channel", 
            "order_total_amount", "order_item_count"
        ]].copy()
        
        # Ensure order_date is mapped correctly
        df_facts["order_date"] = pd.to_datetime(df_facts["order_date"]).dt.date
        
        df_facts.to_sql("fact_orders", conn, if_exists="append", index=False)
        print(f"Loaded {len(df_facts)} fact records into fact_orders.")
        
    print("Warehouse load completed successfully.")
    return True

if __name__ == "__main__":
    dt = sys.argv[1] if len(sys.argv) > 1 else "2026-07-07"
    success = load_data_to_warehouse(dt)
    sys.exit(0 if success else 1)
