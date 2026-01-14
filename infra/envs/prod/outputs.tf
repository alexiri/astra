output "instance_id" {
  value = aws_instance.astra.id
}

output "public_ip" {
  value = aws_instance.astra.public_ip
}

output "public_dns" {
  value = aws_instance.astra.public_dns
}
