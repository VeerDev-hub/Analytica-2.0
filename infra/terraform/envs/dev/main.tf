# Dev: smallest sizes, single-AZ, one NAT, no deletion protection (design 5.3).
#
#   cd infra/terraform/envs/dev
#   terraform init -backend-config=backend.hcl   # see backend.hcl.example
#   terraform plan
#
# Nothing here has been applied. Applying creates billable AWS resources.

terraform {
  required_version = ">= 1.9"
  backend "s3" {} # bucket/key/region/dynamodb_table come from backend.hcl
}

variable "region" {
  type    = string
  default = "us-east-1"
}
variable "image_tag" {
  type    = string
  default = "latest"
}
variable "alarm_email" {
  type    = string
  default = ""
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = "analytica", Environment = "dev", ManagedBy = "terraform" }
  }
}

module "stack" {
  source              = "../../stack"
  name                = "analytica-dev"
  environment         = "dev"
  image_tag           = var.image_tag
  alarm_email         = var.alarm_email
  single_nat_gateway  = true
  db_instance_class   = "db.t4g.small"
  db_multi_az         = false
  redis_node_type     = "cache.t4g.micro"
  api_count           = 1
  worker_count        = 1
  deletion_protection = false
}

output "app_url" { value = module.stack.app_url }
output "ecr_repository_url" { value = module.stack.ecr_repository_url }
output "cluster_name" { value = module.stack.cluster_name }
output "migrate_task_definition" { value = module.stack.migrate_task_definition }
output "private_subnet_ids" { value = module.stack.private_subnet_ids }
output "app_security_group_id" { value = module.stack.app_security_group_id }
output "web_bucket" { value = module.stack.web_bucket }
output "distribution_id" { value = module.stack.distribution_id }
output "app_secret_arn" { value = module.stack.app_secret_arn }
