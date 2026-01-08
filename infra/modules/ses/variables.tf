variable "name" {
  type        = string
  description = "Name prefix (app-env)."
}

variable "domain" {
  type        = string
  description = "SES sending domain (e.g. example.com)."
}

variable "route53_zone_id" {
  type        = string
  description = "Route53 hosted zone ID for the domain."
}

variable "aws_account_id" {
  type        = string
  description = "AWS account ID (used for SNS topic policy condition)."
}

variable "event_webhook_url" {
  type        = string
  description = "Optional public URL for django-ses SESEventWebhookView (e.g. https://example.com/ses/event-webhook/). When set, an SNS subscription is created."
  default     = null
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to resources."
  default     = {}
}
