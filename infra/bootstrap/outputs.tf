output "state_bucket_name" {
  value       = aws_s3_bucket.state.bucket
  description = "S3 bucket used for Terraform remote state."
}

output "state_bucket_arn" {
  value       = aws_s3_bucket.state.arn
  description = "S3 bucket ARN."
}

output "lock_table_name" {
  value       = aws_dynamodb_table.locks.name
  description = "DynamoDB table used for state locking."
}

output "lock_table_arn" {
  value       = aws_dynamodb_table.locks.arn
  description = "DynamoDB table ARN."
}
