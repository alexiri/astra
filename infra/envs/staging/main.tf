provider "aws" {
  region = var.aws_region
}

data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

locals {
  name = "${var.app_name}-${var.environment}"
  tags = {
    app = var.app_name
    env = var.environment
  }

  ansible_known_hosts_path = pathexpand(var.ansible_known_hosts_path)
  ansible_files = [
    "${path.module}/../../ansible/astra_ec2.yml",
    "${path.module}/../../systemd/astra-app@.service",
    "${path.module}/../../systemd/astra-caddy.service",
    "${path.module}/../../systemd/Caddyfile",
    "${path.module}/../../systemd/astra.env.example",
    "${path.module}/../../ansible/files/deploy-prod.sh",
    "${path.module}/../../ansible/files/rollback-prod.sh",
    "${path.module}/../../ansible/files/deploy-prod-sha.sh",
  ]
  ansible_hash = sha256(join("", [for path in local.ansible_files : filesha256(path)]))
}

resource "aws_security_group" "astra" {
  name        = "${local.name}-sg"
  description = "Astra EC2 security group"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  dynamic "ingress" {
    for_each = length(var.allowed_ssh_cidrs) > 0 ? [1] : []
    content {
      description = "SSH"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = var.allowed_ssh_cidrs
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, {
    Name = "${local.name}-sg"
  })
}

resource "aws_instance" "astra" {
  ami                         = data.aws_ami.amazon_linux_2023.id
  instance_type               = var.instance_type
  subnet_id                   = data.aws_subnets.default.ids[0]
  vpc_security_group_ids      = [aws_security_group.astra.id]
  key_name                    = var.key_name
  associate_public_ip_address = true

  user_data = <<-EOF
#!/bin/bash
set -euo pipefail

dnf -y install python3
EOF

  tags = merge(local.tags, {
    Name = local.name
  })
}

resource "null_resource" "configure_instance" {
  triggers = {
    instance_id = aws_instance.astra.id
    config_hash = local.ansible_hash
    app_image   = var.app_image
    caddy_image = var.caddy_image
    cron_jobs   = jsonencode(var.cron_jobs)
  }

  provisioner "local-exec" {
    command = <<-EOT
ansible-playbook \\
  -i '${aws_instance.astra.public_ip},' \\
  -u '${var.ansible_user}' \\
  --private-key '${var.ansible_private_key_path}' \\
  -e 'app_image=${var.app_image}' \\
  -e 'caddy_image=${var.caddy_image}' \\
  -e 'django_settings_module=${var.django_settings_module}' \\
  -e 'ansible_ssh_common_args=-o UserKnownHostsFile=${local.ansible_known_hosts_path} -o StrictHostKeyChecking=yes' \\
  -e 'astra_cron_jobs=${jsonencode(var.cron_jobs)}' \\
  '${path.module}/../../ansible/astra_ec2.yml'
EOT
  }

  depends_on = [aws_instance.astra]
}
