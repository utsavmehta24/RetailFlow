#!/bin/bash
set -e

# Resolve scripts directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Starting RetailFlow Environment Setup ==="

# 1. Spin up Docker containers
echo "Spinning up Docker containers (LocalStack & Postgres)..."
cd "$PROJECT_ROOT"
docker compose up -d || docker-compose up -d

# 2. Check and Download Terraform if not installed globally
TF_BIN="terraform"
if ! command -v terraform &> /dev/null; then
    if [ -f "$PROJECT_ROOT/bin/terraform" ]; then
        TF_BIN="$PROJECT_ROOT/bin/terraform"
    else
        echo "Terraform is not installed globally. Attempting to download for local development..."
        mkdir -p "$PROJECT_ROOT/bin"
        
        OS_TYPE=$(uname | tr '[:upper:]' '[:lower:]')
        ARCH_TYPE=$(uname -m)
        
        # Normalize CPU architectures
        if [ "$ARCH_TYPE" = "x86_64" ]; then
            ARCH_TYPE="amd64"
        elif [ "$ARCH_TYPE" = "aarch64" ] || [ "$ARCH_TYPE" = "arm64" ]; then
            ARCH_TYPE="arm64"
        fi
        
        # Normalize OS
        if [[ "$OS_TYPE" == *"mingw"* || "$OS_TYPE" == *"msys"* || "$OS_TYPE" == *"cygwin"* ]]; then
            OS_TYPE="windows"
            TF_ZIP_NAME="terraform_1.9.2_windows_amd64.zip"
        else
            TF_ZIP_NAME="terraform_1.9.2_${OS_TYPE}_${ARCH_TYPE}.zip"
        fi
        
        TF_URL="https://releases.hashicorp.com/terraform/1.9.2/${TF_ZIP_NAME}"
        echo "Downloading Terraform from $TF_URL..."
        curl -fsSL "$TF_URL" -o "$PROJECT_ROOT/bin/terraform.zip"
        unzip -o "$PROJECT_ROOT/bin/terraform.zip" -d "$PROJECT_ROOT/bin"
        rm "$PROJECT_ROOT/bin/terraform.zip"
        
        if [ "$OS_TYPE" = "windows" ]; then
            TF_BIN="$PROJECT_ROOT/bin/terraform.exe"
        else
            chmod +x "$PROJECT_ROOT/bin/terraform"
            TF_BIN="$PROJECT_ROOT/bin/terraform"
        fi
    fi
fi

# 3. Wait for LocalStack
echo "Waiting for LocalStack S3..."
for i in {1..30}; do
    if curl -s http://localhost:4566/ >/dev/null; then
        echo "LocalStack is ready!"
        break
    fi
    echo "Waiting for LocalStack... ($i/30)"
    sleep 2
done

# 4. Wait for Postgres
echo "Waiting for Postgres..."
for i in {1..30}; do
    if python3 -c "import socket; s = socket.socket(); s.connect(('localhost', 5433))" 2>/dev/null; then
        echo "PostgreSQL is ready!"
        break
    fi
    if python -c "import socket; s = socket.socket(); s.connect(('localhost', 5433))" 2>/dev/null; then
        echo "PostgreSQL is ready!"
        break
    fi
    echo "Waiting for PostgreSQL... ($i/30)"
    sleep 2
done

# 5. Run Terraform
echo "Running Terraform..."
cd "$PROJECT_ROOT/infra"
"$TF_BIN" init
"$TF_BIN" apply -auto-approve

# 6. Apply database schema
echo "Applying database schema..."
cd "$PROJECT_ROOT"
python3 -m pip install sqlalchemy psycopg2-binary --quiet || python -m pip install sqlalchemy psycopg2-binary --quiet

python3 -c "import sqlalchemy; engine = sqlalchemy.create_engine('postgresql://postgres:postgres@localhost:5433/retailflow_dw'); conn = engine.connect(); sql = open('warehouse/schema.sql').read(); conn.execute(sqlalchemy.text(sql)); conn.commit(); print('Schema created successfully.')" || \
python -c "import sqlalchemy; engine = sqlalchemy.create_engine('postgresql://postgres:postgres@localhost:5433/retailflow_dw'); conn = engine.connect(); sql = open('warehouse/schema.sql').read(); conn.execute(sqlalchemy.text(sql)); conn.commit(); print('Schema created successfully.')"

echo "=== Setup completed successfully! ==="
