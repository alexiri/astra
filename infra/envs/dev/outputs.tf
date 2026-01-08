output "alb_dns_name" {
  value       = module.alb.alb_dns_name
  description = "ALB DNS name."
}

# FreeIPA Outputs
output "freeipa_public_ip" {
  value       = module.freeipa.public_ip
  description = "FreeIPA server public IP."
}

output "freeipa_private_ip" {
  value       = module.freeipa.private_ip
  description = "FreeIPA server private IP."
}

output "freeipa_web_ui_url" {
  value       = module.freeipa.ipa_web_ui_url
  description = "FreeIPA web UI URL."
}

output "freeipa_ldap_uri" {
  value       = module.freeipa.ldap_uri
  description = "LDAP URI for application connection."
}

output "freeipa_admin_credentials" {
  value       = "Username: admin / Password: ${var.freeipa_admin_password}"
  description = "FreeIPA admin credentials (dev-only)."
  sensitive   = true
}

output "freeipa_service_credentials" {
  value       = "Username: ${var.freeipa_service_username} / Password: ${var.freeipa_service_password}"
  description = "Service account for app (dev-only)."
  sensitive   = true
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
