output "instance_id" {
  description = "EC2 instance ID — used by fleet_start.sh / fleet_stop.sh"
  value       = aws_instance.fleet.id
}

output "instance_public_ip" {
  description = "Elastic IP — stable across every stop/start, so it's safe to hardcode into ~/.ssh/config or trust as a cached value, unlike a default EC2 public IP."
  value       = aws_eip.fleet.public_ip
}

output "checkpoint_bucket_name" {
  description = "S3 bucket that archives checkpoints + training.log"
  value       = aws_s3_bucket.checkpoints.id
}

output "ssh_private_key_path" {
  description = "Local path to the EC2 login private key — used by fleet_ssh.sh"
  value       = local_sensitive_file.fleet_private_key.filename
}
