# Secrets module
# Stores application secrets in AWS Secrets Manager.
# Terraform generates values so nothing is hard-coded or committed.
#
# Note: generated secrets live in Terraform state (standard Terraform tradeoff).

resource "random_password" "django_secret_key" {
  length  = 64
  special = true
}

resource "aws_secretsmanager_secret" "django_secret_key" {
  name                    = "${var.name}/django/secret_key"
  recovery_window_in_days = var.secret_recovery_window_in_days

  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "django_secret_key" {
  secret_id     = aws_secretsmanager_secret.django_secret_key.id
  secret_string = random_password.django_secret_key.result
}

resource "aws_secretsmanager_secret" "freeipa_service_password" {
  name                    = "${var.name}/freeipa/service_password"
  recovery_window_in_days = var.secret_recovery_window_in_days

  # The FreeIPA service password is an external credential. We create the secret
  # container, but do not set its value in Terraform to avoid writing it to state.
  tags = var.tags
}
