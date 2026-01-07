variable "name" {
  type        = string
  description = "Name prefix (app-env)."
}

variable "vpc_id" {
  type        = string
  description = "VPC ID."
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs for DB subnet group."
}

variable "app_security_group_id" {
  type        = string
  description = "Security group ID of the ECS service; allowed to connect to Postgres."
}

variable "db_name" {
  type        = string
  description = "Initial database name."
  default     = "astra"
}

variable "master_username" {
  type        = string
  description = "Master username."
  default     = "astra"
}

variable "engine_version" {
  type        = string
  description = "Optional PostgreSQL engine version pin (e.g. 15.6). If null, AWS selects the default supported minor version."
  default     = "18.1"
}

variable "instance_class" {
  type        = string
  description = "RDS instance class."
  default     = "db.t4g.micro"
}

variable "allocated_storage_gb" {
  type        = number
  description = "Initial allocated storage (GB)."
  default     = 20
}

variable "max_allocated_storage_gb" {
  type        = number
  description = "Max autoscaled storage (GB)."
  default     = 100
}

variable "backup_retention_days" {
  type        = number
  description = "Backup retention."
  default     = 7
}

variable "multi_az" {
  type        = bool
  description = "Enable Multi-AZ for higher availability."
  default     = false
}

variable "deletion_protection" {
  type        = bool
  description = "Deletion protection (recommended true for prod)."
  default     = false
}

variable "skip_final_snapshot" {
  type        = bool
  description = "Skip final snapshot on destroy (dev/staging convenience)."
  default     = true
}

variable "secret_recovery_window_in_days" {
  type        = number
  description = "Secrets Manager recovery window; 0 forces immediate delete."
  default     = 7
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to resources."
  default     = {}
}
