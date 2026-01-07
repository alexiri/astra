provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  use_route53_validated_https = (
    var.acm_certificate_arn == null
    && trimspace(var.https_domain_name) != ""
    && trimspace(var.https_route53_zone_id) != ""
  )

  # Listener creation must not depend on apply-time ACM validation status.
  enable_https_listener = (
    (var.acm_certificate_arn != null && trimspace(var.acm_certificate_arn) != "")
    || local.use_route53_validated_https
  )

  effective_acm_certificate_arn = (
    var.acm_certificate_arn != null && trimspace(var.acm_certificate_arn) != ""
    ? var.acm_certificate_arn
    : (local.use_route53_validated_https ? aws_acm_certificate_validation.alb_dns[0].certificate_arn : null)
  )
}

resource "aws_acm_certificate" "alb_dns" {
  count = local.use_route53_validated_https ? 1 : 0

  domain_name       = var.https_domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = merge(var.tags, {
    app = var.app_name
    env = var.environment
  })
}

resource "aws_route53_record" "alb_dns_validation" {
  for_each = local.use_route53_validated_https ? {
    for dvo in aws_acm_certificate.alb_dns[0].domain_validation_options : dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  } : {}

  zone_id = var.https_route53_zone_id
  name    = each.value.name
  type    = each.value.type
  ttl     = 60
  records = [each.value.value]
}

resource "aws_acm_certificate_validation" "alb_dns" {
  count = local.use_route53_validated_https ? 1 : 0

  certificate_arn         = aws_acm_certificate.alb_dns[0].arn
  validation_record_fqdns = [for r in aws_route53_record.alb_dns_validation : r.fqdn]
}

locals {
  name = "${var.app_name}-${var.environment}"
  tags = merge(var.tags, {
    app = var.app_name
    env = var.environment
  })
}

module "network" {
  source = "../../modules/network"

  name               = local.name
  vpc_cidr           = var.vpc_cidr
  az_count           = var.az_count
  single_nat_gateway = var.single_nat_gateway
  tags               = local.tags
}

module "alb" {
  source = "../../modules/alb"

  name                = local.name
  vpc_id              = module.network.vpc_id
  public_subnet_ids   = module.network.public_subnet_ids
  target_port         = var.container_port
  enable_https        = local.enable_https_listener
  acm_certificate_arn = local.effective_acm_certificate_arn
  tags                = local.tags
}

resource "aws_route53_record" "alb_https" {
  count = trimspace(var.https_route53_zone_id) != "" && trimspace(var.https_domain_name) != "" ? 1 : 0

  zone_id = var.https_route53_zone_id
  name    = var.https_domain_name
  type    = "A"

  alias {
    name                   = module.alb.alb_dns_name
    zone_id                = module.alb.alb_zone_id
    evaluate_target_health = true
  }
}

resource "aws_security_group" "ecs_service" {
  name        = "${local.name}-svc-sg"
  description = "ECS service security group"
  vpc_id      = module.network.vpc_id

  ingress {
    description     = "App from ALB"
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [module.alb.alb_security_group_id]
  }

  dynamic "ingress" {
    for_each = var.enable_direct_task_ingress ? [1] : []
    content {
      description = "TEMPORARY TEST OVERRIDE: direct access to ECS tasks"
      from_port   = var.container_port
      to_port     = var.container_port
      protocol    = "tcp"
      cidr_blocks = var.direct_task_ingress_cidrs
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, {
    Name = "${local.name}-svc-sg"
  })
}

module "ecr" {
  source          = "../../modules/ecr"
  repository_name = "${var.app_name}-${var.environment}"
  tags            = local.tags
}

module "secrets" {
  source = "../../modules/secrets"
  name   = local.name
  tags   = local.tags
}

module "rds" {
  source = "../../modules/rds"

  name                  = local.name
  vpc_id                = module.network.vpc_id
  private_subnet_ids    = module.network.private_subnet_ids
  app_security_group_id = aws_security_group.ecs_service.id

  db_name         = var.db_name
  master_username = var.db_user

  instance_class           = var.db_instance_class
  allocated_storage_gb     = var.db_allocated_storage_gb
  max_allocated_storage_gb = var.db_max_allocated_storage_gb

  backup_retention_days = var.db_backup_retention_days
  multi_az              = var.db_multi_az
  deletion_protection   = var.db_deletion_protection
  skip_final_snapshot   = var.db_skip_final_snapshot

  tags = local.tags
}

module "ecs" {
  source = "../../modules/ecs"

  name                      = local.name
  aws_region                = var.aws_region
  vpc_id                    = module.network.vpc_id
  subnet_ids                = module.network.public_subnet_ids
  assign_public_ip          = true
  service_security_group_id = aws_security_group.ecs_service.id
  target_group_arn          = module.alb.target_group_arn

  image_repository_url = module.ecr.repository_url
  image_tag            = var.image_tag

  container_port = var.container_port
  desired_count  = var.desired_count
  task_cpu       = var.task_cpu
  task_memory    = var.task_memory

  django_settings_module = var.django_settings_module
  django_debug           = var.django_debug

  allowed_hosts = length(var.allowed_hosts) > 0 ? var.allowed_hosts : (
    var.enable_direct_task_ingress ? ["*"] : (var.django_debug ? [] : [module.alb.alb_dns_name])
  )
  public_base_url    = var.public_base_url
  default_from_email = var.default_from_email
  email_url          = var.email_url

  db_host = module.rds.endpoint
  db_port = module.rds.port
  db_name = module.rds.db_name
  db_user = module.rds.master_username

  db_password_secret_arn              = module.rds.master_password_secret_arn
  django_secret_key_secret_arn        = module.secrets.django_secret_key_secret_arn
  freeipa_service_password_secret_arn = coalesce(var.freeipa_service_password_secret_arn, module.secrets.freeipa_service_password_secret_arn)
  secrets_manager_arns = [
    module.rds.master_password_secret_arn,
    module.secrets.django_secret_key_secret_arn,
    coalesce(var.freeipa_service_password_secret_arn, module.secrets.freeipa_service_password_secret_arn),
  ]

  aws_storage_bucket_name = coalesce(var.aws_storage_bucket_name, "${var.app_name}-${var.environment}-media")
  aws_s3_domain           = coalesce(var.aws_s3_domain, "https://s3.${var.aws_region}.amazonaws.com")
  aws_s3_region_name      = var.aws_s3_region_name
  aws_s3_endpoint_url     = var.aws_s3_endpoint_url
  aws_s3_addressing_style = var.aws_s3_addressing_style
  aws_querystring_auth    = var.aws_querystring_auth

  aws_ses_region_name       = coalesce(var.aws_ses_region_name, var.aws_region)
  aws_ses_configuration_set = var.aws_ses_configuration_set

  freeipa_host         = var.freeipa_host
  freeipa_verify_ssl   = var.freeipa_verify_ssl
  freeipa_service_user = var.freeipa_service_user
  freeipa_admin_group  = var.freeipa_admin_group

  tags = local.tags
}

module "parameters" {
  source = "../../modules/parameters"

  app_name                            = var.app_name
  environment                         = var.environment
  ecs_cluster_name                    = module.ecs.cluster_name
  ecs_service_name                    = module.ecs.service_name
  ecs_subnet_ids                      = module.network.public_subnet_ids
  ecs_tasks_security_group_id         = aws_security_group.ecs_service.id
  ecr_repository_name                 = module.ecr.repository_name
  freeipa_service_password_secret_arn = coalesce(var.freeipa_service_password_secret_arn, module.secrets.freeipa_service_password_secret_arn)
  tags                                = local.tags
}

module "ses" {
  count  = var.enable_ses ? 1 : 0
  source = "../../modules/ses"

  name            = local.name
  domain          = var.ses_domain
  route53_zone_id = var.route53_zone_id
  aws_account_id  = data.aws_caller_identity.current.account_id
  tags            = local.tags
}

module "github_actions_iam" {
  count  = var.create_github_actions_user ? 1 : 0
  source = "../../modules/iam_github_actions"

  user_name      = "${var.app_name}-${var.environment}-github-actions"
  app_name       = var.app_name
  aws_region     = var.aws_region
  aws_account_id = data.aws_caller_identity.current.account_id

  ecr_repository_arns  = [module.ecr.repository_arn]
  ecs_task_role_arns   = [module.ecs.task_execution_role_arn, module.ecs.task_role_arn]
  secrets_inspect_arns = [coalesce(var.freeipa_service_password_secret_arn, module.secrets.freeipa_service_password_secret_arn)]
  tags                 = local.tags
}

module "application" {
  source = "../../modules/application"

  app_name    = var.app_name
  environment = var.environment
  tags        = local.tags
}
