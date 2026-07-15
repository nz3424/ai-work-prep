resource "tls_private_key" "fleet" {
  algorithm = "ED25519"
}

resource "aws_key_pair" "fleet" {
  key_name   = "${var.project_name}-login-key"
  public_key = tls_private_key.fleet.public_key_openssh

  tags = {
    Name = "${var.project_name}-login-key"
  }
}

# Private half never touches git — files/ is gitignored (Task 1) and this
# resource writes with 0600 permissions, matching what ssh requires anyway.
resource "local_sensitive_file" "fleet_private_key" {
  content         = tls_private_key.fleet.private_key_openssh
  filename        = "${path.module}/files/fleet_login_key.pem"
  file_permission = "0600"
}
