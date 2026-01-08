# ECS module
# - ECS cluster
# - CloudWatch log group
# - Task execution role + task role
# - Fargate task definition and service
# - Service security group allows inbound from ALB only
#
# Secrets injection:
# - The task definition references Secrets Manager ARNs. The task execution role is granted
#   secretsmanager:GetSecretValue to those ARNs.

# Fetch current running task to preserve CI/CD-deployed image when var.image_tag is "bootstrap"
data "aws_ecs_service" "current" {
  count        = var.image_tag == "bootstrap" ? 1 : 0
  cluster_arn  = aws_ecs_cluster.this.arn
  service_name = "${var.name}-service"
}

data "aws_ecs_task_definition" "current" {
  count           = var.image_tag == "bootstrap" && length(data.aws_ecs_service.current) > 0 ? 1 : 0
  task_definition = data.aws_ecs_service.current[0].task_definition
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.name}"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

resource "aws_ecs_cluster" "this" {
  name = "${var.name}-cluster"

  setting {
    name  = "containerInsights"
    value = var.container_insights ? "enabled" : "disabled"
  }

  tags = var.tags
}

resource "aws_iam_role" "task_execution" {
  name = "${var.name}-ecs-task-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "task_execution_managed" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "task_execution_secrets" {
  name = "${var.name}-ecs-exec-secrets"
  role = aws_iam_role.task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadTaskSecrets"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = var.secrets_manager_arns
      }
    ]
  })
}

resource "aws_iam_role" "task" {
  name = "${var.name}-ecs-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

locals {
  container_name = "astra"
  
  # When image_tag is "bootstrap", try to preserve the current image from CI/CD
  current_image = try(
    jsondecode(data.aws_ecs_task_definition.current[0].container_definitions)[0].image,
    null
  )
  current_image_tag = local.current_image != null ? split(":", local.current_image)[1] : null
  
  # Use current image tag if available, otherwise fall back to var.image_tag
  effective_image_tag = var.image_tag == "bootstrap" && local.current_image_tag != null ? local.current_image_tag : var.image_tag
  
  image = "${var.image_repository_url}:${local.effective_image_tag}"

  # Django requires CSRF_TRUSTED_ORIGINS when you're behind a TLS-terminating proxy
  # and serving HTTPS. Derive it from PUBLIC_BASE_URL by default, but allow explicit
  # overrides for more complex setups.
  public_base_origin = (
    var.public_base_url != null && var.public_base_url != "" && can(regex("^https?://[^/]+", var.public_base_url))
    ? regex("^https?://[^/]+", var.public_base_url)
    : null
  )
  effective_csrf_trusted_origins = (
    var.csrf_trusted_origins != null
    ? var.csrf_trusted_origins
    : compact([local.public_base_origin])
  )

  environment_map = {
    DJANGO_SETTINGS_MODULE = var.django_settings_module
    DEBUG                  = var.django_debug ? "1" : "0"

    # Database: settings.py supports DATABASE_URL or discrete DATABASE_* vars.
    DATABASE_HOST = var.db_host
    DATABASE_PORT = tostring(var.db_port)
    DATABASE_NAME = var.db_name
    DATABASE_USER = var.db_user

    # Production-required runtime settings.
    ALLOWED_HOSTS        = length(var.allowed_hosts) > 0 ? join(",", var.allowed_hosts) : null
    PUBLIC_BASE_URL      = var.public_base_url
    CSRF_TRUSTED_ORIGINS = length(local.effective_csrf_trusted_origins) > 0 ? join(",", local.effective_csrf_trusted_origins) : null
    DEFAULT_FROM_EMAIL   = var.default_from_email
    EMAIL_URL            = var.email_url

    # S3 storage configuration.
    AWS_STORAGE_BUCKET_NAME = var.aws_storage_bucket_name
    AWS_S3_DOMAIN           = var.aws_s3_domain
    AWS_S3_REGION_NAME      = var.aws_s3_region_name
    AWS_S3_ENDPOINT_URL     = var.aws_s3_endpoint_url
    AWS_S3_ADDRESSING_STYLE = var.aws_s3_addressing_style
    AWS_QUERYSTRING_AUTH    = var.aws_querystring_auth ? "1" : "0"

    # FreeIPA configuration.
    FREEIPA_HOST         = var.freeipa_host
    FREEIPA_VERIFY_SSL   = var.freeipa_verify_ssl ? "1" : "0"
    FREEIPA_SERVICE_USER = var.freeipa_service_user
    FREEIPA_ADMIN_GROUP  = var.freeipa_admin_group

    # SES / email event processing.
    AWS_SES_REGION_NAME       = var.aws_ses_region_name
    AWS_SES_CONFIGURATION_SET = var.aws_ses_configuration_set
  }

  container_environment = [
    for k, v in local.environment_map : {
      name  = k
      value = v
    } if v != null
  ]

  # Health checks use standalone server on port 9000 to avoid Django ALLOWED_HOSTS issues.
  container_healthcheck = {
    command     = ["CMD-SHELL", "python -c \"import urllib.request; r = urllib.request.urlopen('http://localhost:9000/healthz'); exit(0 if r.status == 200 else 1)\" || exit 1"]
    interval    = 30
    timeout     = 5
    retries     = 3
    startPeriod = 30
  }

  container_definitions = [
    {
      name      = local.container_name
      image     = local.image
      essential = true

      portMappings = [
        {
          containerPort = var.container_port
          protocol      = "tcp"
        },
        {
          containerPort = 9000
          protocol      = "tcp"
        }
      ]

      environment = local.container_environment

      secrets = [
        { name = "DATABASE_PASSWORD", valueFrom = var.db_password_secret_arn },
        # Django reads SECRET_KEY from the environment.
        { name = "SECRET_KEY", valueFrom = var.django_secret_key_secret_arn },
        { name = "FREEIPA_SERVICE_PASSWORD", valueFrom = var.freeipa_service_password_secret_arn },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "ecs"
        }
      }

      healthCheck = local.container_healthcheck
    }
  ]
}

resource "aws_ecs_task_definition" "this" {
  family                   = "${var.name}-task"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory

  execution_role_arn = aws_iam_role.task_execution.arn
  task_role_arn      = aws_iam_role.task.arn

  container_definitions = jsonencode(local.container_definitions)

  tags = var.tags
}

resource "aws_ecs_service" "this" {
  name            = "${var.name}-service"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = var.desired_count

  launch_type = "FARGATE"

  network_configuration {
    assign_public_ip = var.assign_public_ip
    subnets          = var.subnet_ids
    security_groups  = [var.service_security_group_id]
  }

  load_balancer {
    target_group_arn = var.target_group_arn
    container_name   = local.container_name
    container_port   = var.container_port
  }

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200

  lifecycle {
    ignore_changes = [desired_count, task_definition]
  }

  tags = var.tags
}
