#!/bin/bash
# Resolve scripts directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Starting RetailFlow Environment Teardown ==="

# 1. Run terraform destroy
TF_BIN="terraform"
if [ -f "$PROJECT_ROOT/bin/terraform" ]; then
    TF_BIN="$PROJECT_ROOT/bin/terraform"
elif [ -f "$PROJECT_ROOT/bin/terraform.exe" ]; then
    TF_BIN="$PROJECT_ROOT/bin/terraform.exe"
fi

if command -v "$TF_BIN" &> /dev/null || command -v terraform &> /dev/null; then
    echo "Destroying Terraform provisioned resources..."
    cd "$PROJECT_ROOT/infra"
    "$TF_BIN" destroy -auto-approve || terraform destroy -auto-approve || echo "Warning: Terraform destroy failed."
    cd "$PROJECT_ROOT"
else
    echo "Warning: Terraform binary not found. Skipping resource destruction."
fi

# 2. Stop and remove Docker containers and volumes
echo "Stopping and destroying Docker containers and volumes..."
docker compose down -v || docker-compose down -v

echo "=== Teardown completed successfully! ==="
