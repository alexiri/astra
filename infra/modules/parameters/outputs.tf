output "parameter_prefix" {
  value       = "/${var.app_name}/${var.environment}"
  description = "SSM parameter prefix used by CI/CD."
}
