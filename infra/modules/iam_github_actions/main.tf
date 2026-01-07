# IAM module for GitHub Actions (long-lived access keys)
# Creates an IAM user and attaches a least-privilege policy for:
# - pushing images to ECR
# - updating ECS services
# - registering task definition revisions
# - running one-off tasks (migrations)
# - reading SSM parameters written by infra/modules/parameters
#
# IMPORTANT: This module intentionally does NOT create access keys.
# Create keys manually in AWS and store them as GitHub secrets.

resource "aws_iam_user" "this" {
  name = var.user_name
  tags = var.tags
}

resource "aws_iam_policy" "deploy" {
  name        = "${var.user_name}-deploy"
  description = "GitHub Actions deploy policy for astra"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Sid    = "ECRAuth"
          Effect = "Allow"
          Action = [
            "ecr:GetAuthorizationToken"
          ]
          Resource = "*"
        },
        {
          Sid    = "ECRPushPull"
          Effect = "Allow"
          Action = [
            "ecr:BatchCheckLayerAvailability",
            "ecr:BatchGetImage",
            "ecr:CompleteLayerUpload",
            "ecr:DescribeImages",
            "ecr:DescribeRepositories",
            "ecr:GetDownloadUrlForLayer",
            "ecr:InitiateLayerUpload",
            "ecr:PutImage",
            "ecr:UploadLayerPart"
          ]
          Resource = var.ecr_repository_arns
        },
        {
          Sid    = "ECSDeploy"
          Effect = "Allow"
          Action = [
            "ecs:DescribeClusters",
            "ecs:DescribeServices",
            "ecs:DescribeTaskDefinition",
            "ecs:ListTasks",
            "ecs:RegisterTaskDefinition",
            "ecs:RunTask",
            "ecs:StopTask",
            "ecs:UpdateService"
          ]
          Resource = "*"
        },
        {
          Sid    = "PassRolesToECS"
          Effect = "Allow"
          Action = [
            "iam:PassRole"
          ]
          Resource = var.ecs_task_role_arns
        },
        {
          Sid    = "ReadSSMParameters"
          Effect = "Allow"
          Action = [
            "ssm:GetParameter",
            "ssm:GetParameters",
            "ssm:GetParametersByPath"
          ]
          Resource = [
            "arn:aws:ssm:${var.aws_region}:${var.aws_account_id}:parameter/${var.app_name}/*"
          ]
        }
      ],
      length(var.secrets_inspect_arns) > 0 ? [
        {
          Sid    = "InspectSecrets"
          Effect = "Allow"
          Action = [
            "secretsmanager:DescribeSecret",
            "secretsmanager:ListSecretVersionIds"
          ]
          Resource = var.secrets_inspect_arns
        }
      ] : []
    )
  })
}

resource "aws_iam_user_policy_attachment" "deploy" {
  user       = aws_iam_user.this.name
  policy_arn = aws_iam_policy.deploy.arn
}
