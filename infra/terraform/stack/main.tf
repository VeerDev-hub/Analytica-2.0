# One Analytica environment: network -> data -> compute -> edge -> observability.

terraform {
  required_version = ">= 1.9"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

variable "name" { type = string }
variable "environment" { type = string }
variable "image_tag" {
  type    = string
  default = "latest"
}
variable "app_origin" {
  type        = string
  default     = ""
  description = "Custom app URL for CORS (https://app.example.com). Not needed when the SPA and API share the CloudFront domain."
}
variable "alb_certificate_arn" {
  type    = string
  default = ""
}
variable "cloudfront_certificate_arn" {
  type    = string
  default = ""
}
variable "domain_aliases" {
  type    = list(string)
  default = []
}
variable "web_acl_arn" {
  type    = string
  default = ""
}
variable "alarm_email" {
  type    = string
  default = ""
}
variable "single_nat_gateway" {
  type    = bool
  default = true
}
variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}
variable "db_multi_az" {
  type    = bool
  default = false
}
variable "redis_node_type" {
  type    = string
  default = "cache.t4g.small"
}
variable "api_count" {
  type    = number
  default = 1
}
variable "worker_count" {
  type    = number
  default = 1
}
variable "deletion_protection" {
  type    = bool
  default = true
}

module "network" {
  source             = "../modules/network"
  name               = var.name
  single_nat_gateway = var.single_nat_gateway
}

# Shared by every ECS task; the data stores only accept connections from this group.
resource "aws_security_group" "app" {
  name   = "${var.name}-app"
  vpc_id = module.network.vpc_id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

module "data" {
  source                = "../modules/data"
  name                  = var.name
  vpc_id                = module.network.vpc_id
  isolated_subnet_ids   = module.network.isolated_subnet_ids
  app_security_group_id = aws_security_group.app.id
  db_instance_class     = var.db_instance_class
  db_multi_az           = var.db_multi_az
  redis_node_type       = var.redis_node_type
  deletion_protection   = var.deletion_protection
}

module "compute" {
  source                = "../modules/compute"
  name                  = var.name
  environment           = var.environment
  vpc_id                = module.network.vpc_id
  public_subnet_ids     = module.network.public_subnet_ids
  private_subnet_ids    = module.network.private_subnet_ids
  app_security_group_id = aws_security_group.app.id
  image_tag             = var.image_tag
  certificate_arn       = var.alb_certificate_arn
  app_origin            = var.app_origin
  db_host               = module.data.db_endpoint
  db_master_secret_arn  = module.data.db_master_secret_arn
  redis_host            = module.data.redis_endpoint
  bucket_name           = module.data.bucket_name
  bucket_arn            = module.data.bucket_arn
  app_secret_arn        = module.data.app_secret_arn
  kms_key_arn           = module.data.kms_key_arn
  api_count             = var.api_count
  worker_count          = var.worker_count
}

module "edge" {
  source                    = "../modules/edge"
  name                      = var.name
  alb_dns_name              = module.compute.alb_dns_name
  alb_https                 = module.compute.alb_https
  aliases                   = var.domain_aliases
  certificate_arn_us_east_1 = var.cloudfront_certificate_arn
  web_acl_arn               = var.web_acl_arn
}

module "observability" {
  source                  = "../modules/observability"
  name                    = var.name
  alarm_email             = var.alarm_email
  alb_arn_suffix          = module.compute.alb_arn_suffix
  target_group_arn_suffix = module.compute.target_group_arn_suffix
  db_identifier           = module.data.db_identifier
  cluster_name            = module.compute.cluster_name
}

output "app_url" { value = "https://${module.edge.domain_name}" }
output "ecr_repository_url" { value = module.compute.ecr_repository_url }
output "cluster_name" { value = module.compute.cluster_name }
output "migrate_task_definition" { value = module.compute.migrate_task_definition }
output "private_subnet_ids" { value = module.network.private_subnet_ids }
output "app_security_group_id" { value = aws_security_group.app.id }
output "web_bucket" { value = module.edge.web_bucket }
output "distribution_id" { value = module.edge.distribution_id }
output "app_secret_arn" { value = module.data.app_secret_arn }
