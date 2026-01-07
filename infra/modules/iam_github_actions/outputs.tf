output "user_name" {
  value       = aws_iam_user.this.name
  description = "IAM user name."
}

output "policy_arn" {
  value       = aws_iam_policy.deploy.arn
  description = "IAM policy ARN attached to the user."
}
