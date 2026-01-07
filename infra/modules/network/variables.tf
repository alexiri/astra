variable "name" {
  type        = string
  description = "Name prefix for resources (typically app-env, e.g. astra-dev)."
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR for the VPC."
  default     = "10.20.0.0/16"
}

variable "az_count" {
  type        = number
  description = "How many AZs to spread subnets across."
  default     = 2
}

variable "single_nat_gateway" {
  type        = bool
  description = "Use a single NAT gateway to reduce cost (recommended for dev/staging)."
  default     = true
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to all resources."
  default     = {}
}
