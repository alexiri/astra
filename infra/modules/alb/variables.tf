variable "name" {
  type        = string
  description = "Name prefix for resources (app-env)."
}

variable "vpc_id" {
  type        = string
  description = "VPC ID."
}

variable "public_subnet_ids" {
  type        = list(string)
  description = "Public subnet IDs for the ALB."
}

variable "target_port" {
  type        = number
  description = "Container port the ALB targets."
  default     = 8000
}

variable "acm_certificate_arn" {
  type        = string
  description = "Optional ACM certificate ARN to enable HTTPS."
  default     = null
}

variable "enable_https" {
  type        = bool
  description = "Whether to enable HTTPS listener and HTTP->HTTPS redirect. Use this when the ACM ARN may be unknown until apply (e.g. DNS validation)."
  default     = null
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to all resources."
  default     = {}
}
