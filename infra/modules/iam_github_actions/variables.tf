variable "user_name" {
  type        = string
  description = "IAM user name for GitHub Actions."
}

variable "app_name" {
  type        = string
  description = "Application name (astra)."
  default     = "astra"
}

variable "aws_region" {
  type        = string
  description = "AWS region (eu-west-1)."
}

variable "aws_account_id" {
  type        = string
  description = "AWS account ID."
}

variable "ecr_repository_arns" {
  type        = list(string)
  description = "ECR repository ARNs that GH Actions can push to."
}

variable "ecs_task_role_arns" {
  type        = list(string)
  description = "Task execution + task roles that GH Actions is allowed to pass to ECS."
}

variable "secrets_inspect_arns" {
  type        = list(string)
  description = "Secrets Manager ARNs that GH Actions may inspect (DescribeSecret/ListSecretVersionIds only; no GetSecretValue)."
  default     = []
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to resources."
  default     = {}
}
