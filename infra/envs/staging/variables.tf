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
  default     = "staging"
}

variable "instance_type" {
  type        = string
  description = "EC2 instance type."
  default     = "t3.small"
}

variable "key_name" {
  type        = string
  description = "EC2 key pair name."
}

variable "allowed_ssh_cidrs" {
  type        = list(string)
  description = "CIDR blocks allowed to access SSH."
  default     = []
}

variable "app_image" {
  type        = string
  description = "Container image for the Astra app."
}

variable "caddy_image" {
  type        = string
  description = "Container image for Caddy."
}
