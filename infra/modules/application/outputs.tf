output "group_name" {
  value       = aws_resourcegroups_group.this.name
  description = "Resource Group name (appears as an Application in the console)."
}

output "group_arn" {
  value       = aws_resourcegroups_group.this.arn
  description = "Resource Group ARN."
}

output "appregistry_application_name" {
  value       = try(aws_servicecatalogappregistry_application.this[0].name, null)
  description = "AppRegistry Application name (if enabled)."
}

output "appregistry_application_arn" {
  value       = try(aws_servicecatalogappregistry_application.this[0].arn, null)
  description = "AppRegistry Application ARN (if enabled)."
}
