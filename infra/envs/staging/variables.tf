variable "aws_region" {
  type    = string
  default = "eu-west-1"
}

variable "app_name" {
  type        = string
  description = "Application name."
  default     = "astra"
}

variable "environment" {
  type        = string
  description = "Environment name."
  default     = "staging"
}

variable "instance_type" {
  type        = string
  description = "EC2 instance type."
  default     = "t3.small"
}

variable "key_name" {
  type        = string
  description = "EC2 key pair name."
}

variable "allowed_ssh_cidrs" {
  type        = list(string)
  description = "CIDR blocks allowed to access SSH."
  default     = []
}

variable "app_image" {
  type        = string
  description = "Container image for the Astra app."
}

variable "caddy_image" {
  type        = string
  description = "Container image for Caddy."
}

variable "ansible_user" {
  type        = string
  description = "SSH user for Ansible."
  default     = "ec2-user"
}

variable "ansible_private_key_path" {
  type        = string
  description = "Path to SSH private key for Ansible."
}

variable "ansible_known_hosts_path" {
  type        = string
  description = "Path to SSH known_hosts for Ansible."
  default     = "~/.ssh/known_hosts"
}

variable "django_settings_module" {
  type        = string
  description = "DJANGO_SETTINGS_MODULE value for the env file."
  default     = "config.settings"
}

variable "cron_jobs" {
  type = list(object({
    name    = string
    command = string
    minute  = optional(string)
    hour    = optional(string)
    day     = optional(string)
    month   = optional(string)
    weekday = optional(string)
  }))
  description = "Cron jobs to configure on the host."
  default = [
    {
      name    = "membership-operations"
      minute  = "0"
      hour    = "0"
      command = "podman exec astra-app-1 python manage.py membership_operations"
    }
  ]
}
