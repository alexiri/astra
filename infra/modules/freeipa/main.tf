# Minimal FreeIPA Server Module for Staging Environment
# Based on fedora-infra/tiny-stage implementation

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

  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }
}

resource "aws_security_group" "ipa" {
  name        = "${var.name_prefix}-ipa-sg"
  description = "Security group for FreeIPA server"
  vpc_id      = var.vpc_id

  # HTTP (for web UI and enrollment)
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = distinct(concat(var.allowed_ingress_cidrs, var.app_security_group_cidrs))
    description = "HTTP for IPA web UI"
  }

  # HTTPS (for web UI)
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = distinct(concat(var.allowed_ingress_cidrs, var.app_security_group_cidrs))
    description = "HTTPS for IPA web UI"
  }

  # LDAP
  ingress {
    from_port   = 389
    to_port     = 389
    protocol    = "tcp"
    cidr_blocks = var.app_security_group_cidrs
    description = "LDAP for application access"
  }

  # LDAPS
  ingress {
    from_port   = 636
    to_port     = 636
    protocol    = "tcp"
    cidr_blocks = var.app_security_group_cidrs
    description = "LDAPS for secure application access"
  }

  # Kerberos
  ingress {
    from_port   = 88
    to_port     = 88
    protocol    = "tcp"
    cidr_blocks = var.app_security_group_cidrs
    description = "Kerberos TCP"
  }

  ingress {
    from_port   = 88
    to_port     = 88
    protocol    = "udp"
    cidr_blocks = var.app_security_group_cidrs
    description = "Kerberos UDP"
  }

  # Kerberos password change
  ingress {
    from_port   = 464
    to_port     = 464
    protocol    = "tcp"
    cidr_blocks = var.app_security_group_cidrs
    description = "Kerberos password change TCP"
  }

  ingress {
    from_port   = 464
    to_port     = 464
    protocol    = "udp"
    cidr_blocks = var.app_security_group_cidrs
    description = "Kerberos password change UDP"
  }

  # DNS (for internal resolution)
  ingress {
    from_port   = 53
    to_port     = 53
    protocol    = "tcp"
    cidr_blocks = var.app_security_group_cidrs
    description = "DNS TCP"
  }

  ingress {
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = var.app_security_group_cidrs
    description = "DNS UDP"
  }

  # SSH for admin access
  dynamic "ingress" {
    for_each = length(var.ssh_allowed_cidrs) > 0 ? [1] : []
    content {
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = var.ssh_allowed_cidrs
      description = "SSH for administration"
    }
  }

  # Allow all outbound
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound"
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-ipa-sg"
  })
}

resource "aws_instance" "ipa" {
  ami           = data.aws_ami.almalinux_10.id
  instance_type = var.instance_type
  key_name      = var.key_name

  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = [aws_security_group.ipa.id]
  associate_public_ip_address = true

  # FreeIPA needs stable hostname
  private_dns_name_options {
    hostname_type = "resource-name"
  }

  # Allocate enough storage for IPA
  root_block_device {
    volume_type = "gp3"
    volume_size = 30
    encrypted   = true
  }

  # User data to set hostname properly before Ansible runs
  user_data = <<-EOF
    #!/bin/bash
    set -euo pipefail

    # Ansible requires a Python interpreter on the target.
    dnf -y install python3 openssh-server firewalld

    # FreeIPA install can temporarily require more RAM than a small instance has.
    # Add swap so pki-tomcatd does not get OOM-killed mid-install.
    if [ ! -f /swapfile ]; then
      fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048
      chmod 600 /swapfile
      mkswap /swapfile
      swapon /swapfile
      echo '/swapfile none swap sw 0 0' >> /etc/fstab
    fi

    # Ensure SSH is reachable for Terraform/Ansible provisioning.
    systemctl enable --now sshd
    systemctl enable --now firewalld
    if command -v firewall-cmd >/dev/null 2>&1; then
      firewall-cmd --permanent --add-service=ssh || true
      firewall-cmd --reload || true
    fi

    hostnamectl set-hostname ${var.ipa_hostname}
    echo "preserve_hostname: true" >> /etc/cloud/cloud.cfg
    
    # Ensure hostname resolves locally
    PRIVATE_IP="$(curl -fsS http://169.254.169.254/latest/meta-data/local-ipv4)"
    echo "$PRIVATE_IP ${var.ipa_hostname} $(hostname -s)" >> /etc/hosts
  EOF

  # FreeIPA provisioning depends on user_data effects; replace the instance if user_data changes.
  user_data_replace_on_change = true

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-ipa"
  })

  lifecycle {
    ignore_changes = [ami] # Don't recreate on AMI updates
  }
}

# Allocate Elastic IP for stable external access
resource "aws_eip" "ipa" {
  count    = var.allocate_eip ? 1 : 0
  domain   = "vpc"
  instance = aws_instance.ipa.id

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-ipa-eip"
  })
}

# Output Ansible inventory details
resource "local_file" "ansible_inventory" {
  count    = var.create_ansible_inventory ? 1 : 0
  filename = "${path.root}/ipa_inventory.ini"

  content = <<-EOF
    [ipa_servers]
    ${var.ipa_hostname} ansible_host=${var.allocate_eip ? aws_eip.ipa[0].public_ip : aws_instance.ipa.public_ip} ansible_user=${var.ansible_user} ansible_ssh_private_key_file=${var.ansible_ssh_key_path}
    
    [ipa_servers:vars]
    ipa_realm=${var.ipa_realm}
    ipa_domain=${var.ipa_domain}
    ipa_hostname=${var.ipa_hostname}
  EOF

  file_permission = "0600"
}
