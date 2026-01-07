variable "name" {
  type        = string
  description = "Name prefix (app-env)."
}

variable "secret_recovery_window_in_days" {
  type        = number
  description = "Secrets Manager recovery window; 0 forces immediate delete."
  default     = 7
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to resources."
  default     = {}
}
