output "alb_dns_name" {
  value       = module.alb.alb_dns_name
  description = "ALB DNS name."
}

output "rds_endpoint" {
  value       = module.rds.endpoint
  description = "RDS endpoint hostname."
}

output "ssm_parameter_prefix" {
  value       = module.parameters.parameter_prefix
  description = "SSM parameter prefix used by CI/CD."
}

output "ecr_repository_url" {
  value       = module.ecr.repository_url
  description = "ECR repository URL (no tag)."
}
