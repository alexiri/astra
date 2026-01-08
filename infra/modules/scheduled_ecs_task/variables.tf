variable "name" {
  type        = string
  description = "Name prefix for the scheduled task."
}

variable "tags" {
  type        = map(string)
  description = "Tags to apply to resources."
  default     = {}
}

variable "enabled" {
  type        = bool
  description = "Whether the schedule is enabled."
  default     = true
}

variable "schedule_expression" {
  type        = string
  description = "EventBridge schedule expression (e.g. rate(1 minute) or cron(...))."
}

variable "description" {
  type        = string
  description = "Human-readable description for the schedule."
  default     = null
}

variable "cluster_arn" {
  type        = string
  description = "ECS cluster ARN to run the task in."
}

variable "task_definition_arn" {
  type        = string
  description = "ECS task definition ARN to run."
}

variable "launch_type" {
  type        = string
  description = "ECS launch type (FARGATE)."
  default     = "FARGATE"
}

variable "task_count" {
  type        = number
  description = "How many tasks to start per schedule tick."
  default     = 1
}

variable "subnet_ids" {
  type        = list(string)
  description = "Subnets for the task ENIs."
}

variable "security_group_ids" {
  type        = list(string)
  description = "Security groups for the task ENIs."
}

variable "assign_public_ip" {
  type        = bool
  description = "Whether to assign a public IP to the task ENI."
  default     = true
}

variable "container_name" {
  type        = string
  description = "Name of the container to override."
}

variable "command" {
  type        = list(string)
  description = "Command override for the container (e.g. [\"python\", \"manage.py\", ...])."
}

variable "pass_role_arns" {
  type        = list(string)
  description = "IAM role ARNs that EventBridge is allowed to pass to ECS (task role + execution role)."
}
