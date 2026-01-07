terraform {
  backend "s3" {
    bucket         = "almalinux-astra-terraform-state"
    key            = "envs/dev/terraform.tfstate"
    region         = "eu-west-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}
