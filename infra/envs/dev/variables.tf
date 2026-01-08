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
  default     = "dev"
}

variable "image_tag" {
  type        = string
  description = "Docker image tag to deploy"
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR."
  default     = "10.20.0.0/16"
}

variable "az_count" {
  type        = number
  description = "AZ count for subnets."
  default     = 2
}

variable "single_nat_gateway" {
  type        = bool
  description = "Use a single NAT gateway (cost optimized)."
  default     = true
}

variable "acm_certificate_arn" {
  type        = string
  description = "Optional ACM certificate ARN for HTTPS."
  default     = null
}

variable "enable_self_signed_https" {
  type        = bool
  description = "If true (and acm_certificate_arn is null), generate/import a self-signed ACM certificate for the ALB HTTPS listener."
  default     = true
}

variable "https_domain_name" {
  type        = string
  description = "DNS name to use for dev HTTPS (must match the certificate). Recommended: create a Route53 record pointing to the ALB."
  default     = "astra-dev-alb-1422845205.eu-west-1.elb.amazonaws.com"

  validation {
    condition     = !var.enable_self_signed_https || (var.https_domain_name != null && trimspace(var.https_domain_name) != "")
    error_message = "https_domain_name must be set when enable_self_signed_https is true."
  }
}

variable "https_route53_zone_id" {
  type        = string
  description = "Optional Route53 hosted zone id to create an ALB alias record for https_domain_name."
  default     = ""
}

variable "container_port" {
  type        = number
  description = "Container port."
  default     = 8000
}

variable "enable_direct_task_ingress" {
  type        = bool
  description = "TEMPORARY DEV/TEST OVERRIDE: when true, allow direct inbound access to ECS tasks on container_port. Leave false for ALB-only ingress."
  default     = false
}

variable "direct_task_ingress_cidrs" {
  type        = list(string)
  description = "CIDR blocks allowed to reach ECS tasks directly when enable_direct_task_ingress=true (e.g. your office IP)."
  default     = ["0.0.0.0/0"]

  validation {
    condition     = !var.enable_direct_task_ingress || length(var.direct_task_ingress_cidrs) > 0
    error_message = "direct_task_ingress_cidrs must be set when enable_direct_task_ingress is true."
  }
}

variable "desired_count" {
  type        = number
  description = "Desired ECS task count."
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
  default     = "alex@almalinux.org"
}

variable "email_url" {
  type        = string
  description = "EMAIL_URL (optional if using SES backend)."
  default     = null
}

variable "enable_send_queued_mail_schedule" {
  type        = bool
  description = "If true, run `python manage.py send_queued_mail` periodically via EventBridge + ECS RunTask."
  default     = true
}

variable "send_queued_mail_schedule_expression" {
  type        = string
  description = "EventBridge schedule expression for send_queued_mail (e.g. rate(1 minute))."
  default     = "rate(1 minute)"
}

variable "enable_membership_operations_schedule" {
  type        = bool
  description = "If true, run `python manage.py membership_operations` periodically via EventBridge + ECS RunTask."
  default     = true
}

variable "membership_operations_schedule_expression" {
  type        = string
  description = "EventBridge schedule expression for membership_operations (e.g. rate(1 day))."
  default     = "rate(1 day)"
}

variable "enable_cleanup_mail_schedule" {
  type        = bool
  description = "If true, run `python manage.py cleanup_mail --days 90 --delete-attachments` periodically via EventBridge + ECS RunTask."
  default     = true
}

variable "cleanup_mail_schedule_expression" {
  type        = string
  description = "EventBridge schedule expression for cleanup_mail (e.g. rate(1 day))."
  default     = "rate(1 day)"
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

# FreeIPA Dev Server Configuration
variable "ssh_key_name" {
  type        = string
  description = "EC2 SSH key pair name for IPA server access."
  default     = null
}

variable "ssh_private_key_path" {
  type        = string
  description = "Path to SSH private key for Ansible automation."
  default     = "~/.ssh/id_rsa"
}

variable "freeipa_hostname" {
  type        = string
  description = "Fully qualified hostname for FreeIPA server (e.g., ipa.dev.example.test)."
  default     = "ipa.astra-dev.test"
}

variable "freeipa_domain" {
  type        = string
  description = "FreeIPA domain (lowercase, e.g., astra-dev.test)."
  default     = "astra-dev.test"
}

variable "freeipa_realm" {
  type        = string
  description = "Kerberos realm for FreeIPA (uppercase, e.g., ASTRA-DEV.TEST)."
  default     = "ASTRA-DEV.TEST"
}

variable "freeipa_admin_password" {
  type        = string
  sensitive   = true
  description = "FreeIPA admin user password (dev-only, hardcoded is ok)."
  default     = "DevPassword123!"
}

variable "freeipa_dm_password" {
  type        = string
  sensitive   = true
  description = "FreeIPA Directory Manager password (dev-only, hardcoded is ok)."
  default     = "DevPassword123!"
}

variable "freeipa_service_username" {
  type        = string
  description = "Service account username for application to bind to LDAP."
  default     = "svc_astra"
}

variable "freeipa_service_password" {
  type        = string
  sensitive   = true
  description = "Service account password for application LDAP bind (will be stored in Secrets Manager)."
  default     = "ServicePassword456!"
}

variable "freeipa_allowed_cidrs" {
  type        = list(string)
  description = "CIDRs allowed to access FreeIPA web UI and SSH (dev-only, defaults to all)."
  default     = ["0.0.0.0/0"]
}

# Application FreeIPA connection settings
# (now points to our dev IPA server, not external demo)
variable "freeipa_host" {
  type        = string
  description = "FREEIPA_HOST for application connection."
  default     = "ipa.astra-dev.test"
}

variable "freeipa_verify_ssl" {
  type        = bool
  description = "FREEIPA_VERIFY_SSL."
  default     = false
}

variable "freeipa_service_user" {
  type        = string
  description = "FREEIPA_SERVICE_USER for application binding."
  default     = "svc_astra"
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
  default     = "db.t4g.micro"
}

variable "db_allocated_storage_gb" {
  type        = number
  description = "RDS storage (GB)."
  default     = 20
}

variable "db_max_allocated_storage_gb" {
  type        = number
  description = "RDS max autoscaled storage (GB)."
  default     = 100
}

variable "db_backup_retention_days" {
  type        = number
  description = "RDS backup retention days."
  default     = 7
}

variable "db_multi_az" {
  type        = bool
  description = "Enable Multi-AZ."
  default     = false
}

variable "db_deletion_protection" {
  type        = bool
  description = "Enable deletion protection."
  default     = false
}

variable "db_skip_final_snapshot" {
  type        = bool
  description = "Skip final snapshot on destroy."
  default     = true
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
