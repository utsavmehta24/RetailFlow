-- DDL for RetailFlow Data Warehouse Star Schema

-- Drop tables if they exist to allow clean rebuilds
DROP TABLE IF EXISTS fact_orders;
DROP TABLE IF EXISTS dim_customer;
DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS dim_date;

-- Create dim_customer
CREATE TABLE dim_customer (
    customer_id VARCHAR(50) PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    segment VARCHAR(50) NOT NULL
);

-- Create dim_product
CREATE TABLE dim_product (
    sku VARCHAR(50) PRIMARY KEY,
    product_name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL
);

-- Create dim_date
CREATE TABLE dim_date (
    full_date DATE PRIMARY KEY,
    date_key INT NOT NULL,
    day_of_week INT NOT NULL,
    day_name VARCHAR(15) NOT NULL,
    month INT NOT NULL,
    month_name VARCHAR(15) NOT NULL,
    quarter INT NOT NULL,
    year INT NOT NULL,
    is_weekend BOOLEAN NOT NULL
);

-- Create fact_orders
CREATE TABLE fact_orders (
    fact_order_key SERIAL PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL,
    customer_id VARCHAR(50) REFERENCES dim_customer(customer_id),
    sku VARCHAR(50) REFERENCES dim_product(sku),
    order_date DATE REFERENCES dim_date(full_date),
    quantity INT NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL,
    line_total NUMERIC(10, 2) NOT NULL,
    channel VARCHAR(50) NOT NULL,
    order_total_amount NUMERIC(10, 2) NOT NULL,
    order_item_count INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
