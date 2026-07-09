variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short name used to prefix/tag all resources"
  type        = string
  default     = "anagrams"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for the public subnets (one per AZ)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "availability_zones" {
  description = "AZs to spread the public subnets across"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "container_port" {
  description = "Port the API container listens on"
  type        = number
  default     = 3001
}

variable "health_check_path" {
  description = "ALB target group health check path"
  type        = string
  default     = "/health"
}

variable "task_cpu" {
  description = "Fargate task CPU units (256 = 0.25 vCPU)"
  type        = number
  default     = 256
}

variable "task_memory" {
  description = "Fargate task memory in MB"
  type        = number
  default     = 512
}

variable "desired_count" {
  description = "Number of API task copies the ECS service keeps running"
  type        = number
  default     = 1
}

variable "db_name" {
  description = "Initial database name"
  type        = string
  default     = "anagrams_app"
}

variable "db_username" {
  description = "Master username for the RDS instance"
  type        = string
  default     = "anagrams_admin"
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_engine_version" {
  description = "MySQL major.minor version"
  type        = string
  default     = "8.0"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage in GB"
  type        = number
  default     = 20
}

variable "jwt_expires_in" {
  description = "JWT expiry, passed through to the API container"
  type        = string
  default     = "2d"
}

variable "client_url" {
  description = "Origin allowed by the API's CORS config — update after the S3/CloudFront client deploy is live"
  type        = string
  default     = "http://localhost:5173"
}
