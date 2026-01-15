output "instance_id" {
  value = aws_instance.astra.id
}

output "public_ip" {
  value = aws_instance.astra.public_ip
}

output "public_dns" {
  value = aws_instance.astra.public_dns
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
