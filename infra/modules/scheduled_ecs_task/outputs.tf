output "rule_arn" {
  value       = aws_cloudwatch_event_rule.this.arn
  description = "ARN of the EventBridge rule."
}

output "event_role_arn" {
  value       = aws_iam_role.eventbridge.arn
  description = "IAM role assumed by EventBridge to run the task."
}
