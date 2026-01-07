output "configuration_set_name" {
  value       = aws_ses_configuration_set.this.name
  description = "SES configuration set name."
}

output "sns_topic_arn" {
  value       = aws_sns_topic.ses_events.arn
  description = "SNS topic ARN receiving SES events."
}

output "identity_arn" {
  value       = aws_ses_domain_identity.domain.arn
  description = "SES domain identity ARN."
}
