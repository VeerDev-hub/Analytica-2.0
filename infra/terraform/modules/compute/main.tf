# ECR, ECS Fargate cluster with api / worker / beat services, a one-off migration task,
# the ALB and least-privilege IAM (design 5.1, 5.2, 5.5).

variable "name" { type = string }
variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "private_subnet_ids" { type = list(string) }
variable "image_tag" {
  type    = string
  default = "latest"
}
variable "certificate_arn" {
  type        = string
  default     = ""
  description = "ACM certificate for the ALB. Empty = HTTP only (CloudFront still serves HTTPS)."
}
variable "app_origin" {
  type        = string
  description = "Browser origin of the SPA, e.g. https://app.example.com (CORS)"
}
variable "db_host" { type = string }
variable "db_master_secret_arn" { type = string }
variable "redis_host" { type = string }
variable "bucket_name" { type = string }
variable "bucket_arn" { type = string }
variable "app_secret_arn" { type = string }
variable "kms_key_arn" { type = string }
variable "app_security_group_id" { type = string }
variable "api_cpu" {
  type    = number
  default = 1024
}
variable "api_memory" {
  type    = number
  default = 2048
}
variable "api_count" {
  type    = number
  default = 2
}
variable "worker_cpu" {
  type    = number
  default = 2048
}
variable "worker_memory" {
  type    = number
  default = 8192
}
variable "worker_count" {
  type    = number
  default = 2
}
variable "chat_model" {
  type    = string
  default = "gemini-2.5-flash"
}
variable "log_retention_days" {
  type    = number
  default = 30
}

data "aws_region" "current" {}

# ------------------------------------------------------------------ registry
resource "aws_ecr_repository" "backend" {
  name                 = "${var.name}-backend"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "KMS" }
}

resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep the last 30 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 30 }
      action       = { type = "expire" }
    }]
  })
}

# ------------------------------------------------------------------ logs
resource "aws_cloudwatch_log_group" "svc" {
  for_each          = toset(["api", "worker", "beat", "migrate"])
  name              = "/ecs/${var.name}/${each.key}"
  retention_in_days = var.log_retention_days
}

# ------------------------------------------------------------------ IAM
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.name}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution_secrets" {
  name = "read-secrets"
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"],
      Resource = [var.app_secret_arn, var.db_master_secret_arn] },
      { Effect = "Allow", Action = ["kms:Decrypt"], Resource = [var.kms_key_arn] },
    ]
  })
}

# Task role: the app's own AWS permissions. Only the data bucket, nothing else.
resource "aws_iam_role" "task" {
  name               = "${var.name}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy" "task_s3" {
  name = "data-bucket"
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:ListBucket"], Resource = [var.bucket_arn],
      Condition = { StringLike = { "s3:prefix" = ["users/*"] } } },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      Resource = ["${var.bucket_arn}/users/*"] },
      { Effect = "Allow", Action = ["kms:Decrypt", "kms:GenerateDataKey"],
      Resource = [var.kms_key_arn] },
    ]
  })
}

# ------------------------------------------------------------------ load balancer
resource "aws_security_group" "alb" {
  name   = "${var.name}-alb"
  vpc_id = var.vpc_id
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group_rule" "app_from_alb" {
  type                     = "ingress"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  security_group_id        = var.app_security_group_id
  source_security_group_id = aws_security_group.alb.id
}

resource "aws_lb" "this" {
  name                       = var.name
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.alb.id]
  subnets                    = var.public_subnet_ids
  drop_invalid_header_fields = true
  idle_timeout               = 300 # chat answers and job progress stream over SSE
}

resource "aws_lb_target_group" "api" {
  name                 = "${var.name}-api"
  port                 = 8000
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = var.vpc_id
  deregistration_delay = 30
  health_check {
    path                = "/api/v1/livez"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = var.certificate_arn == "" ? "forward" : "redirect"
    target_group_arn = var.certificate_arn == "" ? aws_lb_target_group.api.arn : null
    dynamic "redirect" {
      for_each = var.certificate_arn == "" ? [] : [1]
      content {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }
}

resource "aws_lb_listener" "https" {
  count             = var.certificate_arn == "" ? 0 : 1
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# ------------------------------------------------------------------ ECS
resource "aws_ecs_cluster" "this" {
  name = var.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

locals {
  image = "${aws_ecr_repository.backend.repository_url}:${var.image_tag}"
  env = [
    { name = "ENVIRONMENT", value = var.environment },
    { name = "LOG_LEVEL", value = "INFO" },
    { name = "CORS_ORIGINS", value = var.app_origin },
    { name = "DB_HOST", value = var.db_host },
    { name = "REDIS_URL", value = "rediss://${var.redis_host}:6379/0?ssl_cert_reqs=required" },
    { name = "STORAGE_BACKEND", value = "s3" },
    { name = "S3_ENDPOINT_URL", value = "" },
    { name = "S3_BUCKET", value = var.bucket_name },
    { name = "S3_REGION", value = data.aws_region.current.name },
    { name = "CHAT_MODEL", value = var.chat_model },
  ]
  secrets = [
    { name = "DB_PASSWORD", valueFrom = "${var.db_master_secret_arn}:password::" },
    { name = "JWT_SECRET", valueFrom = "${var.app_secret_arn}:JWT_SECRET::" },
    { name = "GEMINI_API_KEY", valueFrom = "${var.app_secret_arn}:GEMINI_API_KEY::" },
  ]
  services = {
    api = {
      cpu = var.api_cpu, memory = var.api_memory
      command = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000",
      "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
    }
    worker = {
      cpu = var.worker_cpu, memory = var.worker_memory
      command = ["celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=INFO",
      "--concurrency=2", "--max-memory-per-child=3000000"]
    }
    beat = {
      cpu = 256, memory = 512
      command = ["celery", "-A", "app.tasks.celery_app", "beat", "--loglevel=INFO",
      "--schedule=/tmp/celerybeat-schedule"]
    }
    migrate = {
      cpu     = 512, memory = 1024
      command = ["alembic", "upgrade", "head"]
    }
  }
}

resource "aws_ecs_task_definition" "svc" {
  for_each                 = local.services
  family                   = "${var.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  container_definitions = jsonencode([{
    name         = each.key
    image        = local.image
    essential    = true
    command      = each.value.command
    environment  = local.env
    secrets      = local.secrets
    portMappings = each.key == "api" ? [{ containerPort = 8000, protocol = "tcp" }] : []
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.svc[each.key].name
        awslogs-region        = data.aws_region.current.name
        awslogs-stream-prefix = each.key
      }
    }
    readonlyRootFilesystem = false
  }])
}

resource "aws_ecs_service" "svc" {
  for_each = {
    api    = var.api_count
    worker = var.worker_count
    beat   = 1
  }
  name                   = each.key
  cluster                = aws_ecs_cluster.this.id
  task_definition        = aws_ecs_task_definition.svc[each.key].arn
  desired_count          = each.value
  launch_type            = "FARGATE"
  enable_execute_command = false
  propagate_tags         = "SERVICE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.app_security_group_id]
    assign_public_ip = false
  }

  dynamic "load_balancer" {
    for_each = each.key == "api" ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.api.arn
      container_name   = "api"
      container_port   = 8000
    }
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle { ignore_changes = [desired_count] } # autoscaling owns it
}

# ------------------------------------------------------------------ autoscaling
resource "aws_appautoscaling_target" "svc" {
  for_each           = { api = [var.api_count, var.api_count * 4], worker = [var.worker_count, var.worker_count * 4] }
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.svc[each.key].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = each.value[0]
  max_capacity       = each.value[1]
}

resource "aws_appautoscaling_policy" "cpu" {
  for_each           = aws_appautoscaling_target.svc
  name               = "${var.name}-${each.key}-cpu"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = each.value.service_namespace
  resource_id        = each.value.resource_id
  scalable_dimension = each.value.scalable_dimension
  target_tracking_scaling_policy_configuration {
    target_value = 60
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

output "cluster_name" { value = aws_ecs_cluster.this.name }
output "ecr_repository_url" { value = aws_ecr_repository.backend.repository_url }
output "alb_dns_name" { value = aws_lb.this.dns_name }
output "alb_arn_suffix" { value = aws_lb.this.arn_suffix }
output "target_group_arn_suffix" { value = aws_lb_target_group.api.arn_suffix }
output "migrate_task_definition" { value = aws_ecs_task_definition.svc["migrate"].family }
output "alb_https" { value = var.certificate_arn != "" }
