# Parameters module
# Stores non-secret deployment metadata in SSM Parameter Store.
# The GitHub Actions workflow reads these parameters at deploy time so it
# doesn’t need hard-coded subnet/SG/service names.

locals {
  prefix = "/${var.app_name}/${var.environment}"
}

resource "aws_ssm_parameter" "cluster_name" {
  name  = "${local.prefix}/ecs/cluster_name"
  type  = "String"
  value = var.ecs_cluster_name

  tags = var.tags
}

resource "aws_ssm_parameter" "service_name" {
  name  = "${local.prefix}/ecs/service_name"
  type  = "String"
  value = var.ecs_service_name

  tags = var.tags
}

resource "aws_ssm_parameter" "ecs_subnet_ids" {
  name  = "${local.prefix}/network/ecs_subnet_ids"
  type  = "StringList"
  value = join(",", var.ecs_subnet_ids)

  tags = var.tags
}

# Backward-compatibility for CI/CD that still reads the older key name.
# The value is intentionally the ECS subnet list (public subnets in the no-NAT architecture).
resource "aws_ssm_parameter" "private_subnet_ids" {
  name  = "${local.prefix}/network/private_subnet_ids"
  type  = "StringList"
  value = join(",", var.ecs_subnet_ids)

  tags = var.tags
}

resource "aws_ssm_parameter" "ecs_tasks_security_group_id" {
  name  = "${local.prefix}/ecs/tasks_security_group_id"
  type  = "String"
  value = var.ecs_tasks_security_group_id

  tags = var.tags
}

resource "aws_ssm_parameter" "ecr_repository_name" {
  name  = "${local.prefix}/ecr/repository_name"
  type  = "String"
  value = var.ecr_repository_name

  tags = var.tags
}

resource "aws_ssm_parameter" "freeipa_service_password_secret_arn" {
  name  = "${local.prefix}/secrets/freeipa_service_password_secret_arn"
  type  = "String"
  value = var.freeipa_service_password_secret_arn

  tags = var.tags
}
