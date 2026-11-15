# Prod: Multi-AZ RDS, NAT per AZ, 2 tasks per service, deletion protection (design 5.2, 5.3).
# For a portfolio/beta budget, see design 5.7-5.8: start from envs/dev sizes instead.

terraform {
  required_version = ">= 1.9"
  backend "s3" {}
}

variable "region" {
  type    = string
  default = "us-east-1"
}
variable "image_tag" { type = string }
variable "alarm_email" { type = string }
variable "domain_aliases" {
  type    = list(string)
  default = []
}
variable "app_origin" {
  type    = string
  default = ""
}
variable "alb_certificate_arn" {
  type    = string
  default = ""
}
variable "cloudfront_certificate_arn" {
  type    = string
  default = ""
}
variable "web_acl_arn" {
  type    = string
  default = ""
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = "analytica", Environment = "prod", ManagedBy = "terraform" }
  }
}

module "stack" {
  source                     = "../../stack"
  name                       = "analytica-prod"
  environment                = "prod"
  image_tag                  = var.image_tag
  alarm_email                = var.alarm_email
  domain_aliases             = var.domain_aliases
  app_origin                 = var.app_origin
  alb_certificate_arn        = var.alb_certificate_arn
  cloudfront_certificate_arn = var.cloudfront_certificate_arn
  web_acl_arn                = var.web_acl_arn
  single_nat_gateway         = false
  db_instance_class          = "db.t4g.medium"
  db_multi_az                = true
  redis_node_type            = "cache.t4g.small"
  api_count                  = 2
  worker_count               = 2
  deletion_protection        = true
}

output "app_url" { value = module.stack.app_url }
output "ecr_repository_url" { value = module.stack.ecr_repository_url }
output "cluster_name" { value = module.stack.cluster_name }
output "migrate_task_definition" { value = module.stack.migrate_task_definition }
output "private_subnet_ids" { value = module.stack.private_subnet_ids }
output "app_security_group_id" { value = module.stack.app_security_group_id }
output "web_bucket" { value = module.stack.web_bucket }
output "distribution_id" { value = module.stack.distribution_id }
