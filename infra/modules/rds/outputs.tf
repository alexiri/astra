output "endpoint" {
  value       = aws_db_instance.this.address
  description = "RDS endpoint hostname."
}

output "port" {
  value       = aws_db_instance.this.port
  description = "RDS port."
}

output "db_name" {
  value       = var.db_name
  description = "Database name."
}

output "master_username" {
  value       = var.master_username
  description = "Master username."
}

output "db_security_group_id" {
  value       = aws_security_group.db.id
  description = "DB security group ID."
}

output "master_password_secret_arn" {
  value       = aws_secretsmanager_secret.db.arn
  description = "Secrets Manager ARN containing the master password."
}
