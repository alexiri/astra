resource "aws_cloudwatch_event_rule" "this" {
  name                = "${var.name}-rule"
  description         = var.description
  schedule_expression = var.schedule_expression
  state               = var.enabled ? "ENABLED" : "DISABLED"

  tags = var.tags
}

resource "aws_iam_role" "eventbridge" {
  name = "${var.name}-eventbridge"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "eventbridge" {
  name = "${var.name}-eventbridge"
  role = aws_iam_role.eventbridge.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "RunTask"
        Effect = "Allow"
        Action = [
          "ecs:RunTask"
        ]
        Resource = [var.task_definition_arn]
        Condition = {
          ArnEquals = {
            "ecs:cluster" = var.cluster_arn
          }
        }
      },
      {
        Sid    = "PassRoles"
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = var.pass_role_arns
      }
    ]
  })
}

locals {
  ecs_overrides = {
    containerOverrides = [
      {
        name    = var.container_name
        command = var.command
      }
    ]
  }
}

resource "aws_cloudwatch_event_target" "ecs" {
  rule      = aws_cloudwatch_event_rule.this.name
  target_id = "${var.name}-ecs"
  arn       = var.cluster_arn
  role_arn  = aws_iam_role.eventbridge.arn

  ecs_target {
    task_definition_arn = var.task_definition_arn
    launch_type         = var.launch_type
    task_count          = var.task_count

    network_configuration {
      subnets          = var.subnet_ids
      security_groups  = var.security_group_ids
      assign_public_ip = var.assign_public_ip
    }
  }

  input = jsonencode(local.ecs_overrides)
}
