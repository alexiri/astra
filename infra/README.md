# Astra AWS Infrastructure (Terraform)

This folder provisions AWS infrastructure for the **astra** Django app.

## What Terraform manages

- One EC2 instance (default `t3.small`) per environment
- Security group for SSH + HTTP/HTTPS
- User data that installs podman and systemd units for the app + Caddy
- Uses the default VPC and its subnets

## What Terraform does NOT do

- Build/push container images
- Configure application secrets (these live in `/etc/astra/astra.env` on the host)

## Environments and state

Environments live under:

- `infra/envs/staging`
- `infra/envs/prod`

Each environment has its own S3 backend key (separate state) in `backend.tf`.

Assumption: the S3 state bucket and DynamoDB lock table already exist:

- `almalinux-astra-terraform-state`
- `terraform-locks`

If you need Terraform to create these for a new account, run the one-time bootstrap stack in `infra/bootstrap` first.

## Systemd + podman layout

User data installs podman and writes systemd units from `infra/systemd`:

- `astra-app@.service` runs two app instances (ports `8001` + `8002`) with `sdnotify=container`.
- `astra-caddy.service` runs Caddy and load-balances to `localhost:8001` and `localhost:8002`.

## Environment file updates

On first boot, `/etc/astra/astra.env` is created with `APP_IMAGE` and `CADDY_IMAGE` plus empty placeholders
for required application settings. Copy `infra/systemd/astra.env.example`, fill in the values, and upload
it to `/etc/astra/astra.env`.

After updating the env file on the host:

```bash
sudo systemctl restart astra-app@1.service astra-app@2.service astra-caddy.service
```
