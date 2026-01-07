# Terraform Remote State Bootstrap

This stack creates the AWS resources needed by the environment backends under `infra/envs/*`:

- S3 bucket for Terraform state (versioned + encrypted)
- DynamoDB table for state locking

It intentionally uses **local state** (do not add a backend block here), because these resources must exist *before* you can use the S3 backend.

## Usage

From the repo root:

- `cd infra/bootstrap`
- `terraform init`
- `terraform apply`

Defaults match the existing backend config in `infra/envs/*/backend.tf`:

- bucket: `almalinux-astra-terraform-state`
- lock table: `terraform-locks`

### Tags

Resources are tagged with:

- `app = astra`
- `env = shared`

Override by setting `-var env=...` or `-var app_name=...`.
