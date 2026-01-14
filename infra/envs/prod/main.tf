resource "local_sensitive_file" "astra_extra_vars" {
  # Keep secrets out of the repo and out of the command line.
  filename = "${path.module}/.terraform/astra_extra_vars.json"
  content = jsonencode({
    database_password        = var.db_password
    freeipa_service_password = var.freeipa_service_password
    # If empty, the Ansible playbook will generate a strong one on the host.
    secret_key = var.secret_key
  })
  file_permission = "0600"
}

provider "aws" {
  region = var.aws_region
}

data "aws_ami" "almalinux_10" {
  most_recent = true
  owners      = ["aws-marketplace"]

  filter {
    name   = "name"
    values = ["AlmaLinux OS 10* x86_64*"]
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

  s3_endpoint_url          = "https://s3.${var.aws_region}.amazonaws.com"
  s3_domain                = local.s3_endpoint_url
  ansible_known_hosts_path = pathexpand(var.ansible_known_hosts_path)
  ansible_files = [
    "${path.module}/../../ansible/astra_ec2.yml",
    "${path.module}/../../systemd/astra-app@.service",
    "${path.module}/../../systemd/astra-caddy.service",
    "${path.module}/../../systemd/Caddyfile.j2",
    "${path.module}/../../systemd/astra.env.example",
    "${path.module}/../../systemd/caddy.env",
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
  ami                         = data.aws_ami.almalinux_10.id
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

resource "aws_security_group" "db" {
  name        = "${local.name}-db-sg"
  description = "Astra Aurora security group"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "Postgres"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.astra.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, {
    Name = "${local.name}-db-sg"
  })
}

resource "aws_db_subnet_group" "aurora" {
  name       = "${local.name}-aurora"
  subnet_ids = data.aws_subnets.default.ids

  tags = merge(local.tags, {
    Name = "${local.name}-aurora"
  })
}

resource "aws_rds_cluster" "astra" {
  cluster_identifier      = "${local.name}-aurora"
  engine                  = "aurora-postgresql"
  engine_version          = var.db_engine_version
  database_name           = var.db_name
  master_username         = var.db_username
  master_password         = var.db_password
  db_subnet_group_name    = aws_db_subnet_group.aurora.name
  vpc_security_group_ids  = [aws_security_group.db.id]
  storage_encrypted       = true
  deletion_protection     = var.db_deletion_protection
  skip_final_snapshot     = var.db_skip_final_snapshot
  backup_retention_period = var.db_backup_retention_days
}

resource "aws_rds_cluster_instance" "astra" {
  identifier          = "${local.name}-aurora-1"
  cluster_identifier  = aws_rds_cluster.astra.id
  instance_class      = var.db_instance_class
  engine              = aws_rds_cluster.astra.engine
  engine_version      = aws_rds_cluster.astra.engine_version
  publicly_accessible = false
}

resource "aws_s3_bucket" "astra_media" {
  bucket        = var.s3_bucket_name
  force_destroy = var.s3_force_destroy

  tags = merge(local.tags, {
    Name = "${local.name}-media"
  })
}

resource "aws_s3_bucket_public_access_block" "astra_media" {
  bucket                  = aws_s3_bucket.astra_media.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "null_resource" "configure_instance" {
  triggers = {
    instance_id   = aws_instance.astra.id
    config_hash   = local.ansible_hash
    app_image     = var.app_image
    caddy_image   = var.caddy_image
    cron_jobs     = jsonencode(var.cron_jobs)
    s3_bucket     = var.s3_bucket_name
    s3_domain     = local.s3_domain
    allowed_hosts = jsonencode(var.allowed_hosts)
    freeipa_host  = var.freeipa_host
  }

  provisioner "local-exec" {
    command = <<-EOT
set -euo pipefail

# StrictHostKeyChecking=yes requires the host key to already exist.
# Populate it automatically so provisioning is non-interactive but still safe.
KNOWN_HOSTS_FILE='${local.ansible_known_hosts_path}'
mkdir -p "$(dirname "$KNOWN_HOSTS_FILE")"
touch "$KNOWN_HOSTS_FILE"
ssh-keygen -R '${aws_instance.astra.public_ip}' -f "$KNOWN_HOSTS_FILE" >/dev/null 2>&1 || true

# Wait for SSH to accept connections with strict host key checking.
for _ in $(seq 1 60); do
  ssh-keyscan -H -t rsa,ecdsa,ed25519 '${aws_instance.astra.public_ip}' >> "$KNOWN_HOSTS_FILE" 2>/dev/null || true
  if ssh -o BatchMode=yes -o ConnectTimeout=5 -o UserKnownHostsFile="$KNOWN_HOSTS_FILE" -o StrictHostKeyChecking=yes \
    -i '${pathexpand(var.ansible_private_key_path)}' '${var.ansible_user}@${aws_instance.astra.public_ip}' true 2>/dev/null; then
    break
  fi
  sleep 5
done

ssh -o BatchMode=yes -o ConnectTimeout=5 -o UserKnownHostsFile="$KNOWN_HOSTS_FILE" -o StrictHostKeyChecking=yes \
  -i '${pathexpand(var.ansible_private_key_path)}' '${var.ansible_user}@${aws_instance.astra.public_ip}' true

ansible-playbook \
  -i '${aws_instance.astra.public_ip},' \
  -u '${var.ansible_user}' \
  --private-key '${pathexpand(var.ansible_private_key_path)}' \
  -e '@${local_sensitive_file.astra_extra_vars.filename}' \
  -e 'app_image=${var.app_image}' \
  -e 'caddy_image=${var.caddy_image}' \
  -e 'django_settings_module=${var.django_settings_module}' \
  -e 's3_bucket_name=${var.s3_bucket_name}' \
  -e 's3_endpoint_url=${local.s3_endpoint_url}' \
  -e 's3_domain=${local.s3_domain}' \
  -e 's3_region_name=${var.aws_region}' \
  -e '${jsonencode({
    database_host          = aws_rds_cluster.astra.endpoint
    database_port          = aws_rds_cluster.astra.port
    database_name          = var.db_name
    database_user          = var.db_username
    allowed_hosts          = var.allowed_hosts
    public_base_url        = var.public_base_url
    default_from_email     = var.default_from_email
    freeipa_host           = var.freeipa_host
    freeipa_verify_ssl     = var.freeipa_verify_ssl
    freeipa_service_user   = var.freeipa_service_user
    django_auto_migrate    = var.django_auto_migrate
    django_migrate_retries = var.django_migrate_retries
})}' \
  -e "ansible_ssh_common_args='-o UserKnownHostsFile=${local.ansible_known_hosts_path} -o StrictHostKeyChecking=yes'" \
  -e '${jsonencode({ astra_cron_jobs = var.cron_jobs })}' \
  '${abspath(path.module)}/../../ansible/astra_ec2.yml'
EOT
}

depends_on = [aws_instance.astra]
}
