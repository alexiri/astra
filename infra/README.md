# Astra AWS Infrastructure (Terraform)

This folder provisions AWS infrastructure for the **astra** Django app.

## What Terraform manages

- VPC with public + private subnets (+ NAT)
- Application Load Balancer (ALB)
- ECS cluster + Fargate service
- ECR repository (immutable tags)
- RDS PostgreSQL
- CloudWatch logs
- IAM roles for ECS tasks
- Secrets Manager secrets (DB password, Django secret key)
- SSM Parameters used by CI/CD (cluster/service/subnets/SG/ECR repo)
- Optional SES domain + SNS event publishing for bounces/complaints

## What Terraform does NOT do

- Build/push container images
- Deploy new images (handled by GitHub Actions)

To prevent Terraform fighting deployments, the ECS service ignores drift of `task_definition` (CI/CD updates it).

## Environments and state

Environments live under:

- `infra/envs/dev`
- `infra/envs/staging`
- `infra/envs/prod`

Each environment has its own S3 backend key (separate state) in `backend.tf`.

Assumption: the S3 state bucket and DynamoDB lock table already exist:

- `almalinux-astra-terraform-state`
- `terraform-locks`

If you need Terraform to create these for a new account, run the one-time bootstrap stack in `infra/bootstrap` first.

## Health checks

- ALB target group health check: `/healthz`
- Container-level health check (inside ECS): `/readyz`

## Secrets injection

ECS task definition injects secrets via Secrets Manager:

- `DATABASE_PASSWORD` from RDS password secret
- `DJANGO_SECRET_KEY` from secrets module

These are referenced by ARN in the task definition, and the **task execution role** is granted `secretsmanager:GetSecretValue` for those ARNs.

## SES (optional)

If `enable_ses = true`, Terraform will:

- Verify `ses_domain` via Route53 (you must provide `route53_zone_id`)
- Enable DKIM
- Create a configuration set
- Publish events to an SNS topic (bounces/complaints/etc)

## CI/CD inputs

CI/CD reads these SSM parameters per environment:

- `/${APP_NAME}/${ENV}/ecs/cluster_name`
- `/${APP_NAME}/${ENV}/ecs/service_name`
- `/${APP_NAME}/${ENV}/network/private_subnet_ids` (StringList)
- `/${APP_NAME}/${ENV}/ecs/tasks_security_group_id`
- `/${APP_NAME}/${ENV}/ecr/repository_name`

See `.github/workflows/deploy.yml`.

## Tagging + “Application” view

All taggable resources are tagged consistently to make them easy to find:

- `app = astra`
- `env = dev|staging|prod`

Each environment also creates an AWS Resource Group (shown as an “Application” in the console)
that automatically includes any resources with matching `app` + `env` tags.
