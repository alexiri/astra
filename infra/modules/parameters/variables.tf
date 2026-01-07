variable "app_name" {
  type        = string
  description = "Application name (astra)."
}

variable "environment" {
  type        = string
  description = "Environment name (dev/staging/prod)."
}

variable "ecs_cluster_name" {
  type        = string
  description = "ECS cluster name."
}

variable "ecs_service_name" {
  type        = string
  description = "ECS service name."
}

variable "ecs_subnet_ids" {
  type        = list(string)
  description = "Subnet IDs to use for ECS tasks and one-off tasks."
}

variable "ecs_tasks_security_group_id" {
  type        = string
  description = "Security group ID attached to ECS tasks."
}

variable "ecr_repository_name" {
  type        = string
  description = "ECR repository name."
}

variable "freeipa_service_password_secret_arn" {
  type        = string
  description = "Secrets Manager ARN for FREEIPA_SERVICE_PASSWORD."
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to resources."
  default     = {}
}
