data "aws_iam_policy_document" "fleet_ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "fleet" {
  name               = "${var.project_name}-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.fleet_ec2_assume_role.json
}

# Scoped to exactly the checkpoint bucket — the instance can read/write its
# own archive and nothing else in the account.
data "aws_iam_policy_document" "fleet_s3_checkpoints" {
  statement {
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.checkpoints.arn,
      "${aws_s3_bucket.checkpoints.arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "fleet_s3_checkpoints" {
  name   = "${var.project_name}-s3-checkpoints"
  role   = aws_iam_role.fleet.id
  policy = data.aws_iam_policy_document.fleet_s3_checkpoints.json
}

resource "aws_iam_instance_profile" "fleet" {
  name = "${var.project_name}-instance-profile"
  role = aws_iam_role.fleet.name
}
