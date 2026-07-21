resource "random_id" "client_bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "client" {
  bucket = "${var.project_name}-client-${random_id.client_bucket_suffix.hex}"

  tags = {
    Name = "${var.project_name}-client"
  }
}

resource "aws_s3_bucket_public_access_block" "client" {
  bucket = aws_s3_bucket.client.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "client" {
  name                              = "${var.project_name}-client-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_function" "spa_routing" {
  name    = "${var.project_name}-spa-routing"
  runtime = "cloudfront-js-1.0"
  comment = "Rewrites extensionless paths to /index.html for SPA routing. Attached only to S3 default behavior; /api/* untouched."
  publish = true
  code    = <<-EOT
    function handler(event) {
        var request = event.request;
        var uri = request.uri;

        if (!uri.includes('.')) {
            request.uri = '/index.html';
        }

        return request;
    }
  EOT
}

resource "aws_cloudfront_distribution" "client" {
  enabled             = true
  default_root_object = "index.html"
  # North America + Europe only — keeps cost down for a low-traffic demo,
  # vs. the default PriceClass_All (every edge location worldwide).
  price_class = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.client.bucket_regional_domain_name
    origin_id                = "s3-client"
    origin_access_control_id = aws_cloudfront_origin_access_control.client.id
  }

  origin {
    # Hardcoded (not aws_lb.main.dns_name) so this distribution can be left
    # standing while the ALB/ECS side is torn down independently to cut
    # costs during a pause. /api/* will 502 until the ALB comes back; when
    # it does, revert to aws_lb.main.dns_name and re-apply.
    domain_name = "anagrams-alb-903958801.us-east-1.elb.amazonaws.com"
    origin_id   = "alb-api"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
      # Default (30s) races the server's own 30s SSE heartbeat interval
      # (server/src/index.js's `setInterval(..., 30000)`), so CloudFront
      # kills the /api/events connection right as the first heartbeat
      # would arrive. 60s is the max allowed without an AWS support
      # quota increase — gives the existing heartbeat cadence 2x margin.
      origin_read_timeout = 60
    }
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-client"
    viewer_protocol_policy = "redirect-to-https"
    # Managed-CachingOptimized
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa_routing.arn
    }
  }

  ordered_cache_behavior {
    path_pattern           = "/api/*"
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "alb-api"
    viewer_protocol_policy = "https-only"
    # Managed-CachingDisabled
    cache_policy_id = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    # Managed-AllViewer
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Name = "${var.project_name}-client-cdn"
  }
}

resource "aws_s3_bucket_policy" "client" {
  bucket = aws_s3_bucket.client.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowCloudFrontServicePrincipal"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.client.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.client.arn
        }
      }
    }]
  })
}
