variable "aws_region" {
  type    = string
  default = "eu-west-1"
}

variable "app_name" {
  type        = string
  description = "Application name."
  default     = "astra"
}

variable "environment" {
  type        = string
  description = "Environment name."
  default     = "prod"
}

variable "image_tag" {
  type        = string
  description = "Docker image tag to deploy (bootstrap only; CI/CD updates ECS service task definition)."
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR."
  default     = "10.40.0.0/16"
}

variable "az_count" {
  type        = number
  description = "AZ count for subnets."
  default     = 2
}

variable "single_nat_gateway" {
  type        = bool
  description = "Use a single NAT gateway (set false for higher AZ resilience)."
  default     = false
}

variable "acm_certificate_arn" {
  type        = string
  description = "ACM certificate ARN for HTTPS (recommended for prod)."
  default     = null
}

variable "https_domain_name" {
  type        = string
  description = "Optional DNS name for ALB HTTPS (ACM DNS validation via https_route53_zone_id when set)."
  default     = ""
}

variable "https_route53_zone_id" {
  type        = string
  description = "Optional Route53 hosted zone id used for ACM DNS validation and (optionally) an ALB alias record for https_domain_name."
  default     = ""
}

variable "container_port" {
  type        = number
  description = "Container port."
  default     = 8000
}

variable "enable_direct_task_ingress" {
  type        = bool
  description = "TEMPORARY TEST OVERRIDE: when true, allow direct inbound access to ECS tasks on container_port. Leave false for ALB-only ingress."
  default     = false
}

variable "direct_task_ingress_cidrs" {
  type        = list(string)
  description = "CIDR blocks allowed to reach ECS tasks directly when enable_direct_task_ingress=true."
  default     = []

  validation {
    condition     = !var.enable_direct_task_ingress || length(var.direct_task_ingress_cidrs) > 0
    error_message = "direct_task_ingress_cidrs must be set when enable_direct_task_ingress is true."
  }
}

variable "desired_count" {
  type        = number
  description = "Desired ECS task count."
  default     = 2
}

variable "task_cpu" {
  type        = string
  description = "Fargate CPU units."
  default     = "512"
}

variable "task_memory" {
  type        = string
  description = "Fargate memory (MiB)."
  default     = "1024"
}

variable "django_settings_module" {
  type        = string
  description = "DJANGO_SETTINGS_MODULE."
  default     = "config.settings"
}

variable "django_debug" {
  type        = bool
  description = "Expose DJANGO_DEBUG=1/0."
  default     = false
}

variable "allowed_hosts" {
  type        = list(string)
  description = "Django ALLOWED_HOSTS (optional; defaults to the ALB DNS name when django_debug=false)."
  default     = []
}

variable "public_base_url" {
  type        = string
  description = "PUBLIC_BASE_URL used for absolute links in email."
  default     = null
}

variable "default_from_email" {
  type        = string
  description = "DEFAULT_FROM_EMAIL override."
  default     = null
}

variable "email_url" {
  type        = string
  description = "EMAIL_URL (optional if using SES backend)."
  default     = null
}

variable "aws_storage_bucket_name" {
  type        = string
  description = "S3 bucket name for django-storages (AWS_STORAGE_BUCKET_NAME)."
  default     = null
}

variable "aws_s3_domain" {
  type        = string
  description = "AWS_S3_DOMAIN (scheme+host/path used to derive media URLs)."
  default     = null
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
  description = "AWS_QUERYSTRING_AUTH."
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

variable "freeipa_host" {
  type        = string
  description = "FREEIPA_HOST."
  default     = "ipa.demo1.freeipa.org"
}

variable "freeipa_private_dns_enabled" {
  type        = bool
  description = "If true, create a Route53 private hosted zone + A record in this VPC for FreeIPA (for VPC-internal name resolution)."
  default     = false
}

variable "freeipa_private_zone_name" {
  type        = string
  description = "Private hosted zone name (e.g. astra-prod.test). Required if freeipa_private_dns_enabled=true."
  default     = null
}

variable "freeipa_private_record_name" {
  type        = string
  description = "Record name to create in the private zone (e.g. ipa.astra-prod.test). Required if freeipa_private_dns_enabled=true."
  default     = null
}

variable "freeipa_private_record_ip" {
  type        = string
  description = "Private IP address for the FreeIPA A record. Required if freeipa_private_dns_enabled=true."
  default     = null
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
  description = "Secrets Manager ARN for FREEIPA_SERVICE_PASSWORD (required)."
  default     = null
}

variable "db_name" {
  type        = string
  description = "Database name."
  default     = "astra"
}

variable "db_user" {
  type        = string
  description = "Database user."
  default     = "astra"
}

variable "db_instance_class" {
  type        = string
  description = "RDS instance class."
  default     = "db.t4g.small"
}

variable "db_allocated_storage_gb" {
  type        = number
  description = "RDS storage (GB)."
  default     = 50
}

variable "db_max_allocated_storage_gb" {
  type        = number
  description = "RDS max autoscaled storage (GB)."
  default     = 200
}

variable "db_backup_retention_days" {
  type        = number
  description = "RDS backup retention days."
  default     = 14
}

variable "db_multi_az" {
  type        = bool
  description = "Enable Multi-AZ."
  default     = true
}

variable "db_deletion_protection" {
  type        = bool
  description = "Enable deletion protection (recommended true for prod)."
  default     = true
}

variable "db_skip_final_snapshot" {
  type        = bool
  description = "Skip final snapshot on destroy (recommended false for prod)."
  default     = false
}

variable "enable_ses" {
  type        = bool
  description = "Whether to manage SES domain + event publishing."
  default     = false
}

variable "ses_domain" {
  type        = string
  description = "SES sending domain (e.g. example.com)."
  default     = ""
}

variable "route53_zone_id" {
  type        = string
  description = "Route53 hosted zone id for ses_domain."
  default     = ""
}

variable "create_github_actions_user" {
  type        = bool
  description = "Create an IAM user + policy for GitHub Actions."
  default     = false
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to all resources."
  default     = {}
}
