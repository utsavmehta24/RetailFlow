import os
import sys
import boto3

# S3 configuration
S3_ENDPOINT = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
RAW_BUCKET = "retailflow-raw"

def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id="mock",
        aws_secret_access_key="mock",
        region_name="us-east-1"
    )

def upload_mock_data(target_date: str):
    s3 = get_s3_client()
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sample_dir = os.path.join(base_dir, "data", "sample_orders")
    
    csv_filename = "pos_export_2026-07-01.csv"
    json_filename = "ecommerce_export_2026-07-01.json"
    
    csv_path = os.path.join(sample_dir, csv_filename)
    json_path = os.path.join(sample_dir, json_filename)
    
    if not os.path.exists(csv_path) or not os.path.exists(json_path):
        print(f"Error: Sample data files not found in {sample_dir}")
        return False
        
    # We upload them under the raw partition for the target date
    s3_csv_key = f"raw/orders/{target_date}/pos_export_{target_date}.csv"
    s3_json_key = f"raw/orders/{target_date}/ecommerce_export_{target_date}.json"
    
    print(f"Uploading {csv_path} to s3://{RAW_BUCKET}/{s3_csv_key}")
    try:
        s3.upload_file(csv_path, RAW_BUCKET, s3_csv_key)
        print("CSV upload successful.")
    except Exception as e:
        print(f"Failed to upload CSV: {e}")
        return False
        
    print(f"Uploading {json_path} to s3://{RAW_BUCKET}/{s3_json_key}")
    try:
        s3.upload_file(json_path, RAW_BUCKET, s3_json_key)
        print("JSON upload successful.")
    except Exception as e:
        print(f"Failed to upload JSON: {e}")
        return False
        
    print(f"All files ingested successfully for date {target_date}")
    return True

if __name__ == "__main__":
    dt = sys.argv[1] if len(sys.argv) > 1 else "2026-07-07"
    success = upload_mock_data(dt)
    sys.exit(0 if success else 1)
