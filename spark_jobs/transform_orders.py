import os
import sys
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, to_date, sum as spark_sum, count as spark_count, round as spark_round
from pyspark.sql.window import Window

def get_spark_session(endpoint: str) -> SparkSession:
    """Build and configure Spark Session for LocalStack S3 (s3a) compatibility"""
    # Use Hadoop-AWS package that matches typical spark installations (Hadoop 3.3.4 for Spark 3.5.x)
    return SparkSession.builder \
        .appName("RetailFlowTransform") \
        .config("spark.jars.packages", "org.apache.hadoop:hadoop-aws:3.4.2") \
        .config("spark.hadoop.fs.s3a.endpoint", endpoint) \
        .config("spark.hadoop.fs.s3a.access.key", "mock") \
        .config("spark.hadoop.fs.s3a.secret.key", "mock") \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false") \
        .config("spark.hadoop.fs.s3a.connection.timeout", "60000") \
        .config("spark.hadoop.fs.s3a.establish.timeout", "60000") \
        .config("spark.hadoop.fs.s3a.connection.establish.timeout", "60000") \
        .config("spark.hadoop.fs.s3a.threads.keepalivetime", "60000") \
        .config("spark.hadoop.fs.s3a.connection.acquisition.timeout", "60000") \
        .getOrCreate()

def run_transformation(target_date: str):
    endpoint = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
    print(f"Initializing PySpark with S3 endpoint: {endpoint}")
    spark = get_spark_session(endpoint)
    
    # Define S3 paths (using s3a scheme for Hadoop AWS connector)
    raw_bucket = "retailflow-raw"
    curated_bucket = "retailflow-curated"
    
    input_path = f"s3a://{raw_bucket}/validated/orders/{target_date}/valid_orders.csv"
    output_path = f"s3a://{curated_bucket}/curated/orders/processed_date={target_date}"
    
    print(f"Reading validated data from: {input_path}")
    
    try:
        # Read validated CSV
        df = spark.read.option("header", "true").option("inferSchema", "true").csv(input_path)
    except Exception as e:
        print(f"Error reading input CSV from S3: {e}")
        spark.stop()
        return False
        
    print("Initial schema:")
    df.printSchema()
    
    # 1. Deduplicate by order_id and sku (remove duplicate items in the same order)
    df_deduped = df.dropDuplicates(["order_id", "sku"])
    
    # 2. Add line item amount (quantity * unit_price)
    df_with_amounts = df_deduped.withColumn("line_total", spark_round(col("quantity") * col("unit_price"), 2))
    
    # 3. Add window functions to compute order-level aggregates for the denormalized record
    order_window = Window.partitionBy("order_id")
    
    df_final = df_with_amounts \
        .withColumn("order_total_amount", spark_round(spark_sum("line_total").over(order_window), 2)) \
        .withColumn("order_item_count", spark_sum("quantity").over(order_window))
        
    print("Transformed data schema:")
    df_final.printSchema()
    
    print(f"Writing curated Parquet to: {output_path}")
    try:
        # Save as Parquet format
        df_final.write.mode("overwrite").parquet(output_path)
        print("Curated Parquet written successfully.")
    except Exception as e:
        print(f"Failed to write Parquet to curated S3: {e}")
        spark.stop()
        return False
        
    spark.stop()
    return True

if __name__ == "__main__":
    dt = sys.argv[1] if len(sys.argv) > 1 else "2026-07-07"
    success = run_transformation(dt)
    sys.exit(0 if success else 1)
