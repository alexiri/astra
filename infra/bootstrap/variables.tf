variable "aws_region" {
  type        = string
  description = "AWS region."
  default     = "eu-west-1"
}

variable "app_name" {
  type        = string
  description = "Application name used for tagging."
  default     = "astra"
}

variable "env" {
  type        = string
  description = "Environment tag for shared state resources."
  default     = "shared"
}

variable "state_bucket_name" {
  type        = string
  description = "S3 bucket name for Terraform remote state. Must be globally unique."
  default     = "almalinux-astra-terraform-state"
}

variable "lock_table_name" {
  type        = string
  description = "DynamoDB table name used for Terraform state locking."
  default     = "terraform-locks"
}

variable "tags" {
  type        = map(string)
  description = "Additional tags to apply to all resources."
  default     = {}
}
