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

output "db_endpoint" {
  value = aws_rds_cluster.astra.endpoint
}

output "db_reader_endpoint" {
  value = aws_rds_cluster.astra.reader_endpoint
}

output "db_port" {
  value = aws_rds_cluster.astra.port
}

output "s3_bucket_name" {
  value = aws_s3_bucket.astra_media.bucket
}

output "s3_domain" {
  value = local.s3_domain
}

output "s3_endpoint_url" {
  value = local.s3_endpoint_url
}
