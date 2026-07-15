# Latest Amazon Linux 2023 AMI, resolved at plan time via SSM — avoids
# hardcoding a region-specific AMI ID that goes stale.
data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_instance" "fleet" {
  ami                    = data.aws_ssm_parameter.al2023_ami.value
  instance_type           = var.instance_type
  subnet_id                 = aws_subnet.fleet.id
  vpc_security_group_ids      = [aws_security_group.fleet_ssh.id]
  iam_instance_profile           = aws_iam_instance_profile.fleet.name
  key_name                          = aws_key_pair.fleet.key_name
  associate_public_ip_address          = true

  # Explicit rather than trusting the AL2023 AMI's default (~8GB) — enough
  # headroom for Python packages (torch, etc., installed later by
  # run_fleet.sh) plus checkpoints/logs, without over-provisioning like the
  # DB2 stack's 2TB (sized for datasets far larger than tinyshakespeare-scale
  # data). Resizable later in-place (bump this value + `terraform apply`,
  # then `growpart`/`xfs_growfs` on the box) if it's ever not enough.
  root_block_device {
    volume_size = 20
    volume_type = "gp3"
  }

  user_data = templatefile("${path.module}/templates/user_data.sh.tpl", {
    github_deploy_key   = file("${path.module}/${var.github_deploy_key_path}")
    github_repo_ssh_url = var.github_repo_ssh_url
  })

  tags = {
    Name = "${var.project_name}-instance"
  }
}

# Elastic IP so the address is stable across every stop/start — matches
# the source DB2-stack workflow's single memorized `ssh <alias>` command
# instead of a dynamic-lookup approach. EIP-to-instance association
# persists automatically across stop/start (standard EC2-VPC behavior),
# no re-association needed in fleet_start.sh.
resource "aws_eip" "fleet" {
  instance = aws_instance.fleet.id
  domain   = "vpc"

  tags = {
    Name = "${var.project_name}-eip"
  }
}
