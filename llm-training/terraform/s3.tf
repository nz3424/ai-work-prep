resource "random_id" "checkpoint_bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "checkpoints" {
  bucket = "${var.project_name}-checkpoints-${random_id.checkpoint_bucket_suffix.hex}"

  tags = {
    Name = "${var.project_name}-checkpoints"
  }
}

resource "aws_s3_bucket_public_access_block" "checkpoints" {
  bucket = aws_s3_bucket.checkpoints.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
