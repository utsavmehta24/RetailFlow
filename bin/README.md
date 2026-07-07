# `bin/` — Local Binaries

This folder holds executables that the project needs at runtime but that are **not installed system-wide**. Keeping them here makes the project self-contained — anyone who clones the repo gets everything they need without touching their global `PATH` or package manager.

---

## What's in here

| File | What it is | Size | Why it's here |
| :--- | :--- | :--- | :--- |
| `terraform.exe` | [Terraform CLI](https://www.terraform.io/) v1.9 (Windows AMD64) | ~87 MB | The **command-line tool** that reads `.tf` files and provisions infrastructure |
| `LICENSE.txt` | HashiCorp Business Source License (BSL 1.1) | — | Bundled by Terraform — required when redistributing the binary |

> **Note:** `terraform.exe` is listed in `.gitignore` — it is auto-downloaded by `setup.ps1` on first run and does not need to be committed to the repo.

---

## Terraform: two binaries, two jobs

This is the most common point of confusion in this project — Terraform uses **two separate binaries** that have completely different roles:

| Binary | Location | What it is | Size |
| :--- | :--- | :--- | :--- |
| **Terraform CLI** | `bin/terraform.exe` | The tool you run — reads `.tf` files, tracks state, calls providers | ~87 MB |
| **AWS Provider plugin** | `infra/.terraform/providers/.../terraform-provider-aws_v5.100.0_x5.exe` | A plugin that Terraform CLI downloads automatically — implements the actual AWS/LocalStack API calls | ~685 MB |

**The CLI** (`bin/terraform.exe`) is what you call directly:
```powershell
bin\terraform.exe init
bin\terraform.exe apply -auto-approve
```

**The provider plugin** lives in `infra/.terraform/` and is **automatically downloaded** the first time you run `terraform init`. It is a generated artifact — listed in `.gitignore` and never committed to the repo. If you delete it, `terraform init` re-downloads it.

---

## Where `terraform.exe` comes from

`setup.ps1` checks for `terraform.exe` at startup. If it is missing, it auto-downloads v1.9.2 from HashiCorp's official releases:

```
https://releases.hashicorp.com/terraform/1.9.2/terraform_1.9.2_windows_amd64.zip
```

You do **not** need to download it manually — just run `setup.ps1`:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

---

## What Terraform does in this project

Terraform reads [`infra/main.tf`](../infra/main.tf) and provisions two S3 buckets inside the locally-running [LocalStack](https://localstack.cloud/) container:

| Bucket | Purpose |
| :--- | :--- |
| `retailflow-raw` | Stores Bronze raw uploads, Silver validated CSVs, and quarantined bad records |
| `retailflow-curated` | Stores Gold-layer Parquet files produced by PySpark |

Using Terraform instead of manual `aws s3 mb` commands means the infrastructure is reproducible — destroy and recreate with one command, state tracked in `infra/terraform.tfstate`.

---

## License note

`terraform.exe` is distributed under the [HashiCorp Business Source License 1.1](https://www.hashicorp.com/bsl). The `LICENSE.txt` file in this directory is required when redistributing the binary. This project uses Terraform only for local development.

Full license: [https://www.hashicorp.com/bsl](https://www.hashicorp.com/bsl)

---

*Back to [project root](../Readme.md)*


---

## Where `terraform.exe` comes from

The `setup.ps1` script checks for `terraform.exe` at startup. If it is missing, it **auto-downloads** the correct version from the official HashiCorp releases page:

```
https://releases.hashicorp.com/terraform/1.9.2/terraform_1.9.2_windows_amd64.zip
```

So this file will be absent on a fresh clone and will appear here after the first run of `setup.ps1`. You do **not** need to download it manually.

```powershell
# This script auto-bootstraps terraform.exe into bin/ if missing
powershell.exe -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

---

## What Terraform does in this project

Terraform reads the configuration in [`infra/main.tf`](../infra/main.tf) and provisions two S3 buckets inside the locally-running [LocalStack](https://localstack.cloud/) container:

| Bucket | Purpose |
| :--- | :--- |
| `retailflow-raw` | Stores raw Bronze uploads, validated Silver CSVs, and quarantined bad records |
| `retailflow-curated` | Stores the final Gold-layer Parquet files produced by PySpark |

Using Terraform here instead of manually calling the AWS CLI means the infrastructure is **reproducible** — anyone can destroy and recreate it with a single command, and the state of what was provisioned is tracked in `infra/terraform.tfstate`.

---

## What this folder does NOT contain

- It does not contain Python packages (those live in your virtual environment via `requirements.txt`).
- It does not contain Java or PySpark JARs (PySpark downloads its own dependencies at runtime via Maven).
- It does not contain the Hadoop winutils binaries — those are in [`hadoop/bin/`](../hadoop/README.md).

---

## License note

`terraform.exe` is distributed under the [HashiCorp Business Source License 1.1](https://www.hashicorp.com/bsl). The `LICENSE.txt` file in this directory is the license that HashiCorp requires to be included when redistributing the binary. This project uses Terraform only for local development purposes.

Full license text: [https://www.hashicorp.com/bsl](https://www.hashicorp.com/bsl)

---

*Back to [project root](../Readme.md)*
