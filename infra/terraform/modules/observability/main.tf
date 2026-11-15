# Alarms from design 5.6: API 5xx, RDS CPU/storage, worker memory. Notifications go to SNS.

variable "name" { type = string }
variable "alarm_email" {
  type    = string
  default = ""
}
variable "alb_arn_suffix" { type = string }
variable "target_group_arn_suffix" { type = string }
variable "db_identifier" { type = string }
variable "cluster_name" { type = string }

resource "aws_sns_topic" "alarms" {
  name = "${var.name}-alarms"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

locals {
  alarms = {
    api-5xx = {
      namespace = "AWS/ApplicationELB", metric = "HTTPCode_Target_5XX_Count", stat = "Sum"
      threshold = 10, period = 300, comparison = "GreaterThanThreshold"
      dims      = { LoadBalancer = var.alb_arn_suffix, TargetGroup = var.target_group_arn_suffix }
    }
    api-latency-p90 = {
      namespace = "AWS/ApplicationELB", metric = "TargetResponseTime", stat = "p90"
      threshold = 2, period = 300, comparison = "GreaterThanThreshold"
      dims      = { LoadBalancer = var.alb_arn_suffix, TargetGroup = var.target_group_arn_suffix }
    }
    rds-cpu = {
      namespace = "AWS/RDS", metric = "CPUUtilization", stat = "Average"
      threshold = 80, period = 300, comparison = "GreaterThanThreshold"
      dims      = { DBInstanceIdentifier = var.db_identifier }
    }
    rds-free-storage = {
      namespace = "AWS/RDS", metric = "FreeStorageSpace", stat = "Minimum"
      threshold = 5 * 1024 * 1024 * 1024, period = 300, comparison = "LessThanThreshold"
      dims      = { DBInstanceIdentifier = var.db_identifier }
    }
    worker-memory = {
      namespace = "AWS/ECS", metric = "MemoryUtilization", stat = "Maximum"
      threshold = 90, period = 300, comparison = "GreaterThanThreshold"
      dims      = { ClusterName = var.cluster_name, ServiceName = "worker" }
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "this" {
  for_each            = local.alarms
  alarm_name          = "${var.name}-${each.key}"
  namespace           = each.value.namespace
  metric_name         = each.value.metric
  statistic           = contains(["Sum", "Average", "Minimum", "Maximum"], each.value.stat) ? each.value.stat : null
  extended_statistic  = contains(["Sum", "Average", "Minimum", "Maximum"], each.value.stat) ? null : each.value.stat
  threshold           = each.value.threshold
  period              = each.value.period
  evaluation_periods  = 2
  comparison_operator = each.value.comparison
  dimensions          = each.value.dims
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
}

output "alarm_topic_arn" { value = aws_sns_topic.alarms.arn }
