output "alb_dns_name" {
  value       = aws_lb.this.dns_name
  description = "Public DNS name of the ALB."
}

output "alb_zone_id" {
  value       = aws_lb.this.zone_id
  description = "Route53 hosted zone id for ALB alias records."
}

output "alb_security_group_id" {
  value       = aws_security_group.alb.id
  description = "ALB security group ID."
}

output "target_group_arn" {
  value       = aws_lb_target_group.app.arn
  description = "Target group ARN for ECS service attachment."
}
