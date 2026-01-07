variable "name" {
  type        = string
  description = "Name prefix (app-env)."
}

variable "aws_region" {
  type        = string
  description = "AWS region (needed for logs config)."
}

variable "vpc_id" {
  type        = string
  description = "VPC ID."
}

variable "subnet_ids" {
  type        = list(string)
  description = "Subnet IDs for ECS tasks (public subnets in the no-NAT architecture)."
}

variable "assign_public_ip" {
  type        = bool
  description = "Whether to assign public IPs to tasks (required when running in public subnets without NAT/VPC endpoints)."
  default     = true
}

variable "service_security_group_id" {
  type        = string
  description = "Security group ID attached to ECS tasks."
}

variable "target_group_arn" {
  type        = string
  description = "ALB target group ARN to attach the service."
}

variable "image_repository_url" {
  type        = string
  description = "ECR repository URL (no tag)."
}

variable "image_tag" {
  type        = string
  description = "Docker image tag to deploy (immutable Git SHA)."
}

variable "container_port" {
  type        = number
  description = "Container port."
  default     = 8000
}

variable "desired_count" {
  type        = number
  description = "Desired task count."
  default     = 1
}

variable "task_cpu" {
  type        = string
  description = "Fargate CPU units."
  default     = "256"
}

variable "task_memory" {
  type        = string
  description = "Fargate memory (MiB)."
  default     = "512"
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch log retention."
  default     = 14
}

variable "container_insights" {
  type        = bool
  description = "Enable ECS Container Insights."
  default     = false
}

variable "django_settings_module" {
  type        = string
  description = "DJANGO_SETTINGS_MODULE value."
  default     = "config.settings"
}

variable "django_debug" {
  type        = bool
  description = "Set DEBUG env var (1/0) for Django."
  default     = false
}

variable "allowed_hosts" {
  type        = list(string)
  description = "Value for Django ALLOWED_HOSTS (comma-separated). Required when django_debug=false."
  default     = []

  validation {
    condition     = var.django_debug || length(var.allowed_hosts) > 0
    error_message = "allowed_hosts must be set when django_debug is false (production settings require ALLOWED_HOSTS)."
  }
}

variable "public_base_url" {
  type        = string
  description = "PUBLIC_BASE_URL used for absolute links in emails."
  default     = null
}

variable "csrf_trusted_origins" {
  type        = list(string)
  description = "Optional CSRF_TRUSTED_ORIGINS list. If unset, derived from PUBLIC_BASE_URL (scheme + host[:port])."
  default     = null
}

variable "default_from_email" {
  type        = string
  description = "DEFAULT_FROM_EMAIL override."
  default     = null
}

variable "email_url" {
  type        = string
  description = "EMAIL_URL (e.g. smtp://...); optional if using SES backend."
  default     = null
}

variable "db_host" {
  type        = string
  description = "Database hostname."
}

variable "db_port" {
  type        = number
  description = "Database port."
  default     = 5432
}

variable "db_name" {
  type        = string
  description = "Database name."
}

variable "db_user" {
  type        = string
  description = "Database user."
}

variable "db_password_secret_arn" {
  type        = string
  description = "Secrets Manager ARN containing DATABASE_PASSWORD."
}

variable "django_secret_key_secret_arn" {
  type        = string
  description = "Secrets Manager ARN containing DJANGO_SECRET_KEY."
}

variable "freeipa_host" {
  type        = string
  description = "FREEIPA_HOST."
  default     = "ipa.demo1.freeipa.org"
}

variable "freeipa_verify_ssl" {
  type        = bool
  description = "FREEIPA_VERIFY_SSL."
  default     = true
}

variable "freeipa_service_user" {
  type        = string
  description = "FREEIPA_SERVICE_USER."
  default     = "admin"
}

variable "freeipa_admin_group" {
  type        = string
  description = "FREEIPA_ADMIN_GROUP."
  default     = "admins"
}

variable "freeipa_service_password_secret_arn" {
  type        = string
  description = "Secrets Manager ARN containing FREEIPA_SERVICE_PASSWORD. Required for app startup."
  default     = null

  validation {
    condition     = var.freeipa_service_password_secret_arn != null && var.freeipa_service_password_secret_arn != ""
    error_message = "freeipa_service_password_secret_arn must be set (the application requires FREEIPA_SERVICE_PASSWORD)."
  }
}

variable "aws_storage_bucket_name" {
  type        = string
  description = "AWS_STORAGE_BUCKET_NAME (required)."
  default     = null

  validation {
    condition     = var.aws_storage_bucket_name != null && var.aws_storage_bucket_name != ""
    error_message = "aws_storage_bucket_name must be set (settings.py requires AWS_STORAGE_BUCKET_NAME)."
  }
}

variable "aws_s3_domain" {
  type        = string
  description = "AWS_S3_DOMAIN (required; scheme+host/path used to derive media URLs)."
  default     = null

  validation {
    condition     = var.aws_s3_domain != null && var.aws_s3_domain != ""
    error_message = "aws_s3_domain must be set (settings.py requires AWS_S3_DOMAIN)."
  }
}

variable "aws_s3_region_name" {
  type        = string
  description = "AWS_S3_REGION_NAME."
  default     = null
}

variable "aws_s3_endpoint_url" {
  type        = string
  description = "AWS_S3_ENDPOINT_URL (optional; useful for MinIO)."
  default     = null
}

variable "aws_s3_addressing_style" {
  type        = string
  description = "AWS_S3_ADDRESSING_STYLE (path or virtual)."
  default     = null
}

variable "aws_querystring_auth" {
  type        = bool
  description = "AWS_QUERYSTRING_AUTH (true/false)."
  default     = false
}

variable "aws_ses_region_name" {
  type        = string
  description = "AWS_SES_REGION_NAME."
  default     = null
}

variable "aws_ses_configuration_set" {
  type        = string
  description = "AWS_SES_CONFIGURATION_SET (optional)."
  default     = null
}

variable "secrets_manager_arns" {
  type        = list(string)
  description = "List of Secrets Manager ARNs the execution role is allowed to read."
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to resources."
  default     = {}
}
