variable "name_prefix" {
  type        = string
  description = "Prefix for resource names"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID where IPA server will run"
}

variable "subnet_id" {
  type        = string
  description = "Subnet ID for IPA server (should be public for internet access)"
}

variable "instance_type" {
  type        = string
  description = "EC2 instance type for IPA server"
  default     = "t3.small" # Minimal for dev, may be slow but functional
}

variable "key_name" {
  type        = string
  description = "SSH key pair name for EC2 instance"
}

variable "ipa_hostname" {
  type        = string
  description = "Fully qualified hostname for IPA server (e.g., ipa.example.test)"
}

variable "ipa_domain" {
  type        = string
  description = "IPA domain (e.g., example.test)"
}

variable "ipa_realm" {
  type        = string
  description = "Kerberos realm (usually uppercase domain, e.g., EXAMPLE.TEST)"
}

variable "ipa_admin_password" {
  type        = string
  sensitive   = true
  description = "IPA admin user password"
}

variable "ipa_dm_password" {
  type        = string
  sensitive   = true
  description = "Directory Manager password"
}

variable "allowed_ingress_cidrs" {
  type        = list(string)
  description = "CIDRs allowed to access IPA web UI"
  default     = ["0.0.0.0/0"]
}

variable "app_security_group_cidrs" {
  type        = list(string)
  description = "CIDRs for applications that need LDAP/Kerberos access"
}

variable "ssh_allowed_cidrs" {
  type        = list(string)
  description = "CIDRs allowed SSH access"
  default     = ["0.0.0.0/0"]
}

variable "allocate_eip" {
  type        = bool
  description = "Whether to allocate an Elastic IP"
  default     = true
}

variable "create_ansible_inventory" {
  type        = bool
  description = "Whether to create Ansible inventory file"
  default     = true
}

variable "ansible_user" {
  type        = string
  description = "SSH user for Ansible"
  default     = "ec2-user"
}

variable "ansible_ssh_key_path" {
  type        = string
  description = "Path to SSH private key for Ansible"
  default     = "~/.ssh/id_rsa"
}

variable "tags" {
  type        = map(string)
  description = "Tags to apply to resources"
  default     = {}
}
