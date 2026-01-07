terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

# RDS module
# - PostgreSQL instance in private subnets
# - DB subnet group
# - Security group allowing inbound from ECS service SG
# - Password generated and stored in Secrets Manager
#
# Note: The generated password will exist in Terraform state (as with any managed secret).

resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-db-subnets"
  subnet_ids = var.private_subnet_ids

  tags = merge(var.tags, {
    Name = "${var.name}-db-subnets"
  })
}

resource "aws_security_group" "db" {
  name        = "${var.name}-db-sg"
  description = "RDS security group"
  vpc_id      = var.vpc_id

  ingress {
    description     = "PostgreSQL from ECS service"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.app_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.name}-db-sg"
  })
}

resource "random_password" "db" {
  length  = 32
  special = true

  # RDS rejects some printable ASCII characters in master passwords.
  # Specifically, it does not allow: '/', '@', '"', or spaces.
  # Constrain special characters to an allowed subset.
  override_special = "!#$%&()*+,-.:;<=>?[]^_{|}~"
}

resource "aws_secretsmanager_secret" "db" {
  name                    = "${var.name}/rds/master_password"
  recovery_window_in_days = var.secret_recovery_window_in_days

  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id     = aws_secretsmanager_secret.db.id
  secret_string = random_password.db.result
}

resource "aws_db_instance" "this" {
  identifier = "${var.name}-postgres"

  engine         = "postgres"
  engine_version = var.engine_version

  instance_class        = var.instance_class
  allocated_storage     = var.allocated_storage_gb
  max_allocated_storage = var.max_allocated_storage_gb

  db_name  = var.db_name
  username = var.master_username
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.db.id]

  multi_az                = var.multi_az
  publicly_accessible     = false
  storage_encrypted       = true
  backup_retention_period = var.backup_retention_days
  deletion_protection     = var.deletion_protection
  skip_final_snapshot     = var.skip_final_snapshot

  tags = merge(var.tags, {
    Name = "${var.name}-postgres"
  })

  depends_on = [aws_secretsmanager_secret_version.db]
}
