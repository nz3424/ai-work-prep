variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short name used to prefix/tag all resources"
  type        = string
  default     = "llm-training-fleet"
}

variable "vpc_cidr" {
  description = "CIDR block for the dedicated fleet VPC"
  type        = string
  default     = "10.1.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for the single public subnet (one instance, one AZ)"
  type        = string
  default     = "10.1.1.0/24"
}

variable "availability_zone" {
  description = "AZ the instance and its subnet live in"
  type        = string
  default     = "us-east-1a"
}

variable "my_ip_cidr" {
  description = "Your current public IP in CIDR form (e.g. 1.2.3.4/32) — SSH ingress is restricted to this. No default on purpose: set it fresh every session via -var or terraform.tfvars, never leave stale."
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type for the training box"
  type        = string
  default     = "t3.medium"
}

variable "github_repo_ssh_url" {
  description = "SSH clone URL for the repo the fleet pulls from"
  type        = string
  default     = "git@github.com:nz3424/ai-work-prep.git"
}

variable "github_deploy_key_path" {
  description = "Local path (relative to this terraform/ dir) to the private half of the read-only GitHub deploy key — generated manually per README, never committed"
  type        = string
  default     = "files/github_deploy_key"
}
