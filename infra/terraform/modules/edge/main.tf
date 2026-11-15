# CloudFront: SPA from a private S3 bucket (OAC), /api/* to the ALB (design 5.1).

variable "name" { type = string }
variable "alb_dns_name" { type = string }
variable "alb_https" {
  type    = bool
  default = false
}
variable "aliases" {
  type    = list(string)
  default = []
}
variable "certificate_arn_us_east_1" {
  type        = string
  default     = ""
  description = "ACM certificate in us-east-1 for custom domains. Empty = *.cloudfront.net."
}
variable "web_acl_arn" {
  type        = string
  default     = ""
  description = "Optional WAFv2 web ACL (CLOUDFRONT scope, us-east-1) with managed rules"
}

resource "aws_s3_bucket" "web" {
  bucket_prefix = "${var.name}-web-"
}

resource "aws_s3_bucket_public_access_block" "web" {
  bucket                  = aws_s3_bucket.web.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "${var.name}-web"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# Client-side routes (/projects/123) fall back to index.html; files and /api pass through.
resource "aws_cloudfront_function" "spa" {
  name    = "${var.name}-spa-rewrite"
  runtime = "cloudfront-js-2.0"
  code    = <<-JS
    function handler(event) {
      var r = event.request;
      if (!r.uri.startsWith('/api/') && r.uri.indexOf('.') === -1) { r.uri = '/index.html'; }
      return r;
    }
  JS
}

data "aws_cloudfront_cache_policy" "optimized" { name = "Managed-CachingOptimized" }
data "aws_cloudfront_cache_policy" "disabled" { name = "Managed-CachingDisabled" }
data "aws_cloudfront_origin_request_policy" "all_but_host" { name = "Managed-AllViewerExceptHostHeader" }
data "aws_cloudfront_response_headers_policy" "security" { name = "Managed-SecurityHeadersPolicy" }

resource "aws_cloudfront_distribution" "this" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  aliases             = var.aliases
  price_class         = "PriceClass_100"
  web_acl_id          = var.web_acl_arn == "" ? null : var.web_acl_arn
  comment             = var.name

  origin {
    origin_id                = "web"
    domain_name              = aws_s3_bucket.web.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }

  origin {
    origin_id   = "api"
    domain_name = var.alb_dns_name
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = var.alb_https ? "https-only" : "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
      origin_read_timeout    = 60
    }
  }

  default_cache_behavior {
    target_origin_id           = "web"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.optimized.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security.id
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa.arn
    }
  }

  ordered_cache_behavior {
    path_pattern             = "/api/*"
    target_origin_id         = "api"
    viewer_protocol_policy   = "https-only"
    allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = false # don't buffer SSE streams
    cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_but_host.id
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    cloudfront_default_certificate = var.certificate_arn_us_east_1 == ""
    acm_certificate_arn            = var.certificate_arn_us_east_1 == "" ? null : var.certificate_arn_us_east_1
    ssl_support_method             = var.certificate_arn_us_east_1 == "" ? null : "sni-only"
    minimum_protocol_version       = "TLSv1.2_2021"
  }
}

resource "aws_s3_bucket_policy" "web" {
  bucket = aws_s3_bucket.web.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "CloudFrontRead"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.web.arn}/*"
      Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.this.arn } }
    }]
  })
}

output "web_bucket" { value = aws_s3_bucket.web.bucket }
output "distribution_id" { value = aws_cloudfront_distribution.this.id }
output "domain_name" { value = aws_cloudfront_distribution.this.domain_name }
