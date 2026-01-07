variable "repository_name" {
  type        = string
  description = "ECR repository name."
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to resources."
  default     = {}
}
