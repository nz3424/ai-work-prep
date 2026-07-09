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
