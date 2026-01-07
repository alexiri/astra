variable "app_name" {
  type        = string
  description = "Application name (astra)."
}

variable "environment" {
  type        = string
  description = "Environment name (dev/staging/prod)."
}

variable "tags" {
  type        = map(string)
  description = "Base tags applied to the resource group (merged with app/env/Name)."
  default     = {}
}

variable "enable_appregistry" {
  type        = bool
  description = "Also create an AWS Service Catalog AppRegistry Application (shows up in the 'myApplications' console view)."
  default     = true
}

variable "description" {
  type        = string
  description = "Optional description for the AppRegistry application."
  default     = null
}
