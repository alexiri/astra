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

  app_unit   = file("${path.module}/../../systemd/astra-app@.service")
  caddy_unit = file("${path.module}/../../systemd/astra-caddy.service")
  caddyfile  = file("${path.module}/../../systemd/Caddyfile")
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

dnf -y install podman

mkdir -p /etc/astra /var/lib/caddy

cat >/etc/systemd/system/astra-app@.service <<'UNIT'
${local.app_unit}
UNIT

cat >/etc/systemd/system/astra-caddy.service <<'UNIT'
${local.caddy_unit}
UNIT

cat >/etc/astra/Caddyfile <<'CADDY'
${local.caddyfile}
CADDY

cat >/etc/astra/astra.env <<'ENV'
APP_IMAGE=${var.app_image}
CADDY_IMAGE=${var.caddy_image}
DJANGO_SETTINGS_MODULE=config.settings
FREEIPA_SERVICE_PASSWORD=
AWS_STORAGE_BUCKET_NAME=
AWS_S3_DOMAIN=
PUBLIC_BASE_URL=
DATABASE_URL=
ENV

systemctl daemon-reload
systemctl enable --now astra-app@1.service astra-app@2.service astra-caddy.service
EOF

  tags = merge(local.tags, {
    Name = local.name
  })
}
