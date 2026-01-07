output "cluster_name" {
  value       = aws_ecs_cluster.this.name
  description = "ECS cluster name."
}

output "service_name" {
  value       = aws_ecs_service.this.name
  description = "ECS service name."
}

output "service_security_group_id" {
  value       = var.service_security_group_id
  description = "Security group ID for ECS tasks."
}

output "task_family" {
  value       = aws_ecs_task_definition.this.family
  description = "Task definition family (used by CI/CD to register revisions)."
}

output "log_group_name" {
  value       = aws_cloudwatch_log_group.app.name
  description = "CloudWatch log group name."
}

output "task_execution_role_arn" {
  value       = aws_iam_role.task_execution.arn
  description = "Task execution role ARN (needed for iam:PassRole in CI/CD)."
}

output "task_role_arn" {
  value       = aws_iam_role.task.arn
  description = "Task role ARN (needed for iam:PassRole in CI/CD)."
}
