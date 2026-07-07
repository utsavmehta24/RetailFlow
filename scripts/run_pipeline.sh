#!/bin/bash
set -e

# Resolve scripts directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

TARGET_DATE=${1:-"2026-07-01"}

# Set environment variables for PySpark
export PYSPARK_PYTHON=python
export PYSPARK_DRIVER_PYTHON=python

# Dynamically resolve JAVA_HOME if java is in the PATH
if command -v java &>/dev/null; then
    JAVA_PATH=$(which java)
    # Follow symlinks if necessary
    if [ -L "$JAVA_PATH" ]; then
        JAVA_PATH=$(readlink -f "$JAVA_PATH")
    fi
    JAVA_DIR=$(dirname "$(dirname "$JAVA_PATH")")
    export JAVA_HOME="$JAVA_DIR"
fi

echo "=== Running RetailFlow Pipeline for date: $TARGET_DATE ==="

# Step 1: Upload Raw Files to S3 Lake
echo ""
echo "[Step 1/4] Ingesting raw POS & E-commerce exports..."
python3 "$PROJECT_ROOT/ingestion/upload_to_lake.py" "$TARGET_DATE" || python "$PROJECT_ROOT/ingestion/upload_to_lake.py" "$TARGET_DATE"

# Step 2: Schema Validation (Pydantic)
echo ""
echo "[Step 2/4] Validating records and separating quarantined data..."
python3 "$PROJECT_ROOT/validators/order_schema.py" "$TARGET_DATE" || python "$PROJECT_ROOT/validators/order_schema.py" "$TARGET_DATE"

# Step 3: Spark Transformation (PySpark)
echo ""
echo "[Step 3/4] Running PySpark transformation (clean, dedupe, window aggregates)..."
python3 "$PROJECT_ROOT/spark_jobs/transform_orders.py" "$TARGET_DATE" || python "$PROJECT_ROOT/spark_jobs/transform_orders.py" "$TARGET_DATE"

# Step 4: Load to Postgres Warehouse
echo ""
echo "[Step 4/4] Loading curated Parquet to PostgreSQL database..."
python3 "$PROJECT_ROOT/warehouse/load_to_postgres.py" "$TARGET_DATE" || python "$PROJECT_ROOT/warehouse/load_to_postgres.py" "$TARGET_DATE"

echo ""
echo "=== Pipeline run completed successfully for $TARGET_DATE! ==="
