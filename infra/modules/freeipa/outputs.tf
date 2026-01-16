output "instance_id" {
  value       = aws_instance.ipa.id
  description = "EC2 instance ID"
}

output "private_ip" {
  value       = aws_instance.ipa.private_ip
  description = "Private IP address"
}

output "public_ip" {
  value       = var.allocate_eip ? aws_eip.ipa[0].public_ip : aws_instance.ipa.public_ip
  description = "Public IP address"
}

output "security_group_id" {
  value       = aws_security_group.ipa.id
  description = "Security group ID"
}

output "ipa_hostname" {
  value       = var.ipa_hostname
  description = "IPA server hostname"
}

output "ipa_web_ui_url" {
  value       = "https://${var.ipa_hostname}/"
  description = "IPA web UI URL"
}

output "ldap_uri" {
  value       = "ldaps://${var.ipa_hostname}"
  description = "LDAP URI for applications"
}

output "ansible_inventory_path" {
  value       = try(local_file.ansible_inventory[0].filename, "")
  description = "Path to the generated Ansible inventory for the FreeIPA instance"
}
