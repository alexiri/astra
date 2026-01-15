output "instance_id" {
  value = aws_instance.astra.id
}

output "public_ip" {
  value = aws_instance.astra.public_ip
}

output "public_dns" {
  value = aws_instance.astra.public_dns
}

output "freeipa_instance_id" {
  value = module.freeipa.instance_id
}

output "freeipa_public_ip" {
  value = module.freeipa.public_ip
}

output "freeipa_ldap_uri" {
  value = module.freeipa.ldap_uri
}
