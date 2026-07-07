import csv
import json
import os
import sys
import boto3
from datetime import date
from typing import Literal, Dict, Any, List
from io import StringIO
from pydantic import BaseModel, PositiveInt, Field, ValidationError

# S3 configuration
S3_ENDPOINT = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
RAW_BUCKET = "retailflow-raw"

# Define Pydantic Schema for Order Validation (Pydantic v2 style)
class OrderRecord(BaseModel):
    order_id: str = Field(..., min_length=1)
    customer_id: str = Field(..., min_length=1)
    order_date: date
    sku: str = Field(..., min_length=1)
    quantity: PositiveInt
    unit_price: float = Field(..., gt=0)
    channel: Literal["pos", "ecommerce", "marketplace"]

def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id="mock",
        aws_secret_access_key="mock",
        region_name="us-east-1"
    )

def validate_records(records: List[Dict[str, Any]], channel_type: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Validates records, returns (valid_records, quarantined_records)"""
    valid = []
    quarantined = []
    
    for record in records:
        # Pre-process raw data fields to correct types (e.g. quantity from string to int)
        processed = {}
        for k, v in record.items():
            if v == "" or v is None:
                processed[k] = None
            else:
                processed[k] = v
        
        # Try converting numeric strings before validation
        try:
            if processed.get("quantity") is not None:
                processed["quantity"] = int(processed["quantity"])
        except ValueError:
            pass
        
        try:
            if processed.get("unit_price") is not None:
                processed["unit_price"] = float(processed["unit_price"])
        except ValueError:
            pass

        # If channel is not set, default it to the file's channel type
        if not processed.get("channel"):
            processed["channel"] = channel_type

        try:
            # Validate with Pydantic
            validated_record = OrderRecord(**processed)
            # Store date as string for serialization
            item = validated_record.model_dump()
            item["order_date"] = item["order_date"].isoformat()
            valid.append(item)
        except ValidationError as e:
            # Quarantine the bad record with validation details
            quarantined.append({
                "raw_record": record,
                "errors": e.errors(include_url=False),
                "error_message": str(e)
            })
            
    return valid, quarantined

def run_validation_for_date(target_date: str):
    s3 = get_s3_client()
    print(f"Starting validation for date: {target_date}")
    
    # List files in raw bucket under raw/orders/YYYY-MM-DD
    prefix = f"raw/orders/{target_date}/"
    try:
        response = s3.list_objects_v2(Bucket=RAW_BUCKET, Prefix=prefix)
    except Exception as e:
        print(f"Error listing raw objects: {e}")
        return False
        
    if "Contents" not in response:
        print(f"No raw files found under prefix: {prefix}")
        return False

    all_valid = []
    all_quarantined = []

    for obj in response["Contents"]:
        key = obj["Key"]
        filename = os.path.basename(key)
        if not filename:
            continue
            
        print(f"Reading and validating S3 object: {key}")
        
        # Download object content
        s3_obj = s3.get_object(Bucket=RAW_BUCKET, Key=key)
        content = s3_obj["Body"].read().decode("utf-8")
        
        records = []
        channel_hint = "pos" if "pos" in filename.lower() else "ecommerce"
        
        if filename.endswith(".csv"):
            reader = csv.DictReader(StringIO(content))
            records = list(reader)
        elif filename.endswith(".json") or filename.endswith(".jsonl"):
            content_stripped = content.strip()
            if content_stripped.startswith("[") and content_stripped.endswith("]"):
                records = json.loads(content_stripped)
            else:
                for line in content.splitlines():
                    if line.strip():
                        records.append(json.loads(line))
        else:
            print(f"Skipping unsupported file: {filename}")
            continue

        valid, quarantined = validate_records(records, channel_hint)
        all_valid.extend(valid)
        all_quarantined.extend(quarantined)

    # Save valid records back to S3
    if all_valid:
        valid_key = f"validated/orders/{target_date}/valid_orders.csv"
        # Write to a CSV in memory
        csv_buffer = StringIO()
        if all_valid:
            writer = csv.DictWriter(csv_buffer, fieldnames=list(all_valid[0].keys()))
            writer.writeheader()
            writer.writerows(all_valid)
            
        s3.put_object(
            Bucket=RAW_BUCKET,
            Key=valid_key,
            Body=csv_buffer.getvalue().encode("utf-8")
        )
        print(f"Uploaded {len(all_valid)} valid records to s3://{RAW_BUCKET}/{valid_key}")
    else:
        print("No valid records found to write.")

    # Save quarantined records back to S3
    if all_quarantined:
        quarantine_key = f"quarantine/orders/{target_date}/quarantined_orders.jsonl"
        jsonl_content = "\n".join(json.dumps(q) for q in all_quarantined)
        s3.put_object(
            Bucket=RAW_BUCKET,
            Key=quarantine_key,
            Body=jsonl_content.encode("utf-8")
        )
        print(f"Uploaded {len(all_quarantined)} quarantined records to s3://{RAW_BUCKET}/{quarantine_key}")
    else:
        print("No records quarantined.")

    return True

if __name__ == "__main__":
    # Get date from argument or default
    dt = sys.argv[1] if len(sys.argv) > 1 else "2026-07-07"
    success = run_validation_for_date(dt)
    sys.exit(0 if success else 1)
