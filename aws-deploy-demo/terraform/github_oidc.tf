data "aws_iam_policy_document" "github_actions_assume_role" {
  statement {
    sid     = "GitHubActionsOIDC"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:nz3424/ai-work-prep:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # AWS validates GitHub's OIDC tokens against its own trusted root CA list
  # and ignores this value for github's provider specifically, but the
  # Terraform resource still requires a thumbprint to be set. This is
  # GitHub's well-known intermediate CA thumbprint, unchanged since the
  # provider was introduced.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

# --- github-actions-api-deploy: ECR push, ECS task def + service update ---

data "aws_iam_policy_document" "github_actions_api_deploy" {
  statement {
    sid       = "ECRAuth"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "ECRPush"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [aws_ecr_repository.api.arn]
  }

  statement {
    sid       = "ECSTaskDefinition"
    effect    = "Allow"
    actions   = ["ecs:RegisterTaskDefinition", "ecs:DescribeTaskDefinition"]
    resources = ["*"]
  }

  statement {
    sid       = "ECSServiceUpdate"
    effect    = "Allow"
    actions   = ["ecs:UpdateService", "ecs:DescribeServices"]
    resources = [aws_ecs_service.api.id]
  }

  statement {
    sid       = "PassECSRoles"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.ecs_execution.arn, aws_iam_role.ecs_task.arn]
  }
}

resource "aws_iam_role" "github_actions_api_deploy" {
  name               = "github-actions-api-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume_role.json
}

resource "aws_iam_role_policy" "github_actions_api_deploy" {
  name   = "github-actions-api-deploy-policy"
  role   = aws_iam_role.github_actions_api_deploy.id
  policy = data.aws_iam_policy_document.github_actions_api_deploy.json
}

# --- github-actions-frontend-deploy: S3 sync + CloudFront invalidation ---

data "aws_iam_policy_document" "github_actions_frontend_deploy" {
  statement {
    sid       = "S3ClientWrite"
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.client.arn}/*"]
  }

  statement {
    sid       = "S3ClientList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.client.arn]
  }

  statement {
    sid       = "CloudFrontInvalidate"
    effect    = "Allow"
    actions   = ["cloudfront:CreateInvalidation", "cloudfront:GetInvalidation"]
    resources = [aws_cloudfront_distribution.client.arn]
  }
}

resource "aws_iam_role" "github_actions_frontend_deploy" {
  name               = "github-actions-frontend-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume_role.json
}

resource "aws_iam_role_policy" "github_actions_frontend_deploy" {
  name   = "github-actions-frontend-deploy-policy"
  role   = aws_iam_role.github_actions_frontend_deploy.id
  policy = data.aws_iam_policy_document.github_actions_frontend_deploy.json
}
