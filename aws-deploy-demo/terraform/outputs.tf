output "alb_dns_name" {
  description = "Public URL for the API (behind the ALB)"
  value       = "http://${aws_lb.main.dns_name}"
}

output "ecr_repository_url" {
  description = "Push images here before the ECS service can start healthy"
  value       = aws_ecr_repository.api.repository_url
}

output "rds_endpoint" {
  description = "RDS instance address (for running schema.sql migrations)"
  value       = aws_db_instance.main.address
}

output "secrets_manager_arn" {
  description = "Secret containing DB_PASSWORD and JWT_SECRET"
  value       = aws_secretsmanager_secret.app.arn
}

output "cloudfront_domain_name" {
  description = "Public HTTPS URL for the deployed client app"
  value       = "https://${aws_cloudfront_distribution.client.domain_name}"
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID, needed for cache invalidations"
  value       = aws_cloudfront_distribution.client.id
}

output "client_bucket_name" {
  description = "S3 bucket holding the built client assets"
  value       = aws_s3_bucket.client.bucket
}

output "aws_region" {
  description = "Region GitHub Actions workflows should target"
  value       = var.aws_region
}

output "ecs_cluster_name" {
  description = "ECS cluster name, needed by deploy-api.yml"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "ECS service name, needed by deploy-api.yml"
  value       = aws_ecs_service.api.name
}

output "ecs_task_family" {
  description = "ECS task definition family, needed by deploy-api.yml"
  value       = aws_ecs_task_definition.api.family
}

output "github_actions_api_role_arn" {
  description = "IAM role GitHub Actions assumes via OIDC to deploy the API"
  value       = aws_iam_role.github_actions_api_deploy.arn
}

output "github_actions_frontend_role_arn" {
  description = "IAM role GitHub Actions assumes via OIDC to deploy the frontend"
  value       = aws_iam_role.github_actions_frontend_deploy.arn
}
