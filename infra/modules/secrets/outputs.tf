output "django_secret_key_secret_arn" {
  value       = aws_secretsmanager_secret.django_secret_key.arn
  description = "Secrets Manager ARN containing DJANGO_SECRET_KEY."
}

output "freeipa_service_password_secret_arn" {
  value       = aws_secretsmanager_secret.freeipa_service_password.arn
  description = "Secrets Manager ARN containing FREEIPA_SERVICE_PASSWORD (value must be populated out-of-band)."
}
