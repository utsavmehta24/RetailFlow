# `infra/` — Infrastructure as Code (Terraform)

This folder defines the **cloud infrastructure** of the project using [Terraform](https://www.terraform.io/) — the industry-standard Infrastructure as Code (IaC) tool. Instead of manually clicking through a web console or running one-off CLI commands to create S3 buckets, the entire infrastructure is declared in code, versioned in Git, and reproducible on any machine with a single command.

---

## Files

| File | Purpose |
| :--- | :--- |
| `main.tf` | Provider configuration + S3 bucket resource declarations |
| `variables.tf` | Input variables (region, bucket names) with defaults |
| `outputs.tf` | Output values printed after `terraform apply` (bucket names) |
| `terraform.tfstate` | Current state of provisioned resources (auto-managed by Terraform) |
| `terraform.tfstate.backup` | Previous state backup (auto-managed by Terraform) |
| `.terraform.lock.hcl` | Provider version lock file — ensures reproducible provider downloads |

> **Note:** The `.terraform/` directory (provider plugin cache) and state files are listed in `.gitignore` — they are generated artifacts and should never be committed.

---

## Two Terraform binaries — understand the difference

Terraform uses **two completely separate executables** that serve different roles:

| Binary | Location | Role | Size |
| :--- | :--- | :--- | :--- |
| **Terraform CLI** | `../bin/terraform.exe` | The tool you invoke — reads `.tf` files, plans, applies, tracks state | ~87 MB |
| **AWS Provider plugin** | `.terraform/providers/.../terraform-provider-aws_v5.100.0_x5.exe` | Auto-downloaded plugin — implements the actual S3/AWS API calls | ~685 MB |

The provider plugin lives in `.terraform/` and is **downloaded automatically** when you run `terraform init`. It is a generated artifact:
- Listed in `.gitignore` — do not commit it
- If deleted, `terraform init` re-downloads it
- You never call it directly — Terraform CLI invokes it internally

---

## What gets provisioned

Terraform creates two S3 buckets inside the locally-running [LocalStack](https://localstack.cloud/) container:

| Bucket | Variable | Purpose |
| :--- | :--- | :--- |
| `retailflow-raw` | `var.raw_bucket_name` | Bronze layer (raw uploads) + Silver layer (validated CSVs) + Quarantine zone |
| `retailflow-curated` | `var.curated_bucket_name` | Gold layer (Parquet files written by PySpark) |

---

## How the LocalStack provider is configured

`main.tf` overrides the AWS provider endpoint to point at LocalStack instead of real AWS:

```hcl
provider "aws" {
  access_key                  = "mock_access_key"
  secret_key                  = "mock_secret_key"
  region                      = var.aws_region
  s3_use_path_style           = true        # Required for LocalStack
  skip_credentials_validation = true        # Skip real AWS credential check
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    s3 = "http://127.0.0.1:4566"           # LocalStack S3 endpoint
  }
}
```

To **deploy to real AWS**, remove the `endpoints` block, set `skip_*` to `false`, and provide real AWS credentials via environment variables or `~/.aws/credentials`. The resource declarations in `main.tf` require zero changes.

---

## Variables

Defined in `variables.tf` with sensible defaults:

```hcl
variable "aws_region"          { default = "us-east-1" }
variable "raw_bucket_name"     { default = "retailflow-raw" }
variable "curated_bucket_name" { default = "retailflow-curated" }
```

Override any variable without editing the file:

```bash
# Example: deploy to a different region with custom bucket names
terraform apply -var="aws_region=eu-west-1" \
                -var="raw_bucket_name=my-raw-bucket"
```

---

## Terraform state files

`terraform.tfstate` tracks what Terraform has actually provisioned. Terraform uses this to:
- Know which resources already exist (avoid re-creating them)
- Compute the diff between current state and desired state (`terraform plan`)
- Know what to destroy when you run `terraform destroy`

These files are auto-managed — do not edit them manually.

> **Note:** In a real team environment, the state file would be stored in a remote backend (e.g. [S3 + DynamoDB locking](https://developer.hashicorp.com/terraform/language/settings/backends/s3)) so multiple engineers don't overwrite each other's state. For this local project, the default local file backend is sufficient.

---

## Common commands

All Terraform commands run from this directory using the binary in [`../bin/terraform.exe`](../bin/README.md):

```bash
# Show what will be created/changed without actually doing it
../bin/terraform.exe plan

# Create or update resources
../bin/terraform.exe apply -auto-approve

# Show all provisioned resources and their current state
../bin/terraform.exe show

# Destroy everything (removes both S3 buckets from LocalStack)
../bin/terraform.exe destroy -auto-approve
```

The project's automation scripts in [`scripts/`](../scripts/README.md) call these commands for you — you don't need to run them manually during a normal pipeline run.

---

## Why use Terraform instead of `aws s3 mb`?

| Approach | Problem |
| :--- | :--- |
| `aws s3 mb s3://bucket` | Manual, not reproducible, no state tracking, can't diff |
| Boto3 script to create bucket | Code-only, not idempotent without extra checks |
| **Terraform** | Declarative, idempotent, state-tracked, identical to production AWS usage |

Using Terraform here means the exact same `.tf` files can provision real AWS resources in a CI/CD pipeline or production environment — it's not a "local-only" shortcut.

---

## What this folder does NOT contain

- It does not configure the PostgreSQL database schema — that is [`warehouse/schema.sql`](../warehouse/README.md).
- It does not start Docker containers — that is [`scripts/setup.ps1`](../scripts/README.md) + `docker-compose.yml`.
- It does not create Glue databases, RDS instances, or IAM roles — this project is local-only, but the pattern extends directly to those resources.

---

## Related links

- [Terraform documentation](https://developer.hashicorp.com/terraform/docs)
- [Terraform AWS provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [LocalStack Terraform integration](https://docs.localstack.cloud/user-guide/integrations/terraform/)
- [Terraform state management](https://developer.hashicorp.com/terraform/language/state)
- [Terraform S3 bucket resource](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket)

---

*Back to [project root](../Readme.md)*
