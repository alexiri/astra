# SES module
# - Verifies a domain identity (requires Route53 hosted zone)
# - Enables DKIM
# - Creates a configuration set
# - Publishes bounce/complaint/delivery/etc events to an SNS topic
#
# Assumptions:
# - You have a Route53 Hosted Zone for var.domain and pass its zone ID.
# - SES domain verification and DKIM require creating DNS records.

resource "aws_sns_topic" "ses_events" {
  name = "${var.name}-ses-events"
  tags = var.tags
}

# Allow SES to publish to this SNS topic.
resource "aws_sns_topic_policy" "ses_events" {
  arn = aws_sns_topic.ses_events.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowSESPublish"
        Effect = "Allow"
        Principal = {
          Service = "ses.amazonaws.com"
        }
        Action   = "SNS:Publish"
        Resource = aws_sns_topic.ses_events.arn
        Condition = {
          StringEquals = {
            "AWS:SourceAccount" = var.aws_account_id
          }
        }
      }
    ]
  })
}

resource "aws_ses_domain_identity" "domain" {
  domain = var.domain
}

resource "aws_route53_record" "verification" {
  zone_id = var.route53_zone_id
  name    = "_amazonses.${var.domain}"
  type    = "TXT"
  ttl     = 300
  records = [aws_ses_domain_identity.domain.verification_token]
}

resource "aws_ses_domain_dkim" "domain" {
  domain = aws_ses_domain_identity.domain.domain
}

resource "aws_route53_record" "dkim" {
  count = 3

  zone_id = var.route53_zone_id
  name    = "${aws_ses_domain_dkim.domain.dkim_tokens[count.index]}._domainkey.${var.domain}"
  type    = "CNAME"
  ttl     = 300
  records = ["${aws_ses_domain_dkim.domain.dkim_tokens[count.index]}.dkim.amazonses.com"]
}

resource "aws_ses_configuration_set" "this" {
  name = "${var.name}-ses"
}

resource "aws_ses_event_destination" "sns" {
  name                   = "sns"
  configuration_set_name = aws_ses_configuration_set.this.name
  enabled                = true

  matching_types = ["send", "delivery", "bounce", "complaint", "reject", "open", "click"]

  sns_destination {
    topic_arn = aws_sns_topic.ses_events.arn
  }
}

locals {
  webhook_url_set = var.event_webhook_url != null && trimspace(var.event_webhook_url) != ""
  webhook_protocol = (
    local.webhook_url_set && can(regex("^https://", var.event_webhook_url))
    ? "https"
    : "http"
  )
}

resource "aws_sns_topic_subscription" "ses_events_webhook" {
  count = local.webhook_url_set ? 1 : 0

  topic_arn = aws_sns_topic.ses_events.arn
  protocol  = local.webhook_protocol
  endpoint  = var.event_webhook_url

  # django-ses expects SNS's normal JSON envelope, not raw message delivery.
  raw_message_delivery = false
}
