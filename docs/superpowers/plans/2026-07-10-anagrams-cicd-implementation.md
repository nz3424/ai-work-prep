# Anagrams CI/CD Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `docs/superpowers/specs/2026-07-10-anagrams-cicd-design.md` into working artifacts: a Terraform file provisioning GitHub OIDC + two least-privilege IAM deploy roles, and four GitHub Actions workflows (`validate-api.yml`, `validate-frontend.yml`, `deploy-api.yml`, `deploy-frontend.yml`) implementing the PR-gated build → merge → deploy flow described in the spec.

**Architecture:** One new Terraform file (`github_oidc.tf`) adds an OIDC provider and two IAM roles scoped to exactly the AWS actions each deploy workflow needs; `outputs.tf` gains six new outputs so those roles' ARNs and the existing cluster/service/bucket identifiers can be copied into GitHub repo variables without hand-typing ARNs. Two `pull_request`-triggered "validate" workflows always run and always report a fast green check (skipping real work when the PR doesn't touch their subtree), so they're safe to mark as required status checks without deadlocking unrelated PRs. Two `push`-triggered "deploy" workflows stay path-filtered at the trigger level and only fire for real anagrams changes, assuming their OIDC role, building/pushing, and rolling out via ECS/S3+CloudFront with a smoke test.

**Tech Stack:** Terraform (AWS provider ~> 5.0, following existing `aws_iam_policy_document` conventions in `iam.tf`), GitHub Actions (`aws-actions/configure-aws-credentials@v4`, `aws-actions/amazon-ecr-login@v2`, `aws-actions/amazon-ecs-render-task-definition@v1`, `aws-actions/amazon-ecs-deploy-task-definition@v2`, `dorny/paths-filter@v3`, `actions/setup-node@v4`), AWS CLI, `gh` CLI.

## Global Constraints

- Repo is `nz3424/ai-work-prep` (confirmed via `git remote -v`) — OIDC trust conditions and `gh` commands use this exact slug.
- **Scope stops at `terraform plan` and local file validation.** No task in this plan runs `terraform apply`, pushes to `main`, sets GitHub repo variables, opens a PR, or touches branch protection — those are real, hard-to-reverse, shared-state changes (billable IAM roles; a branch-protection rule that removes admin bypass on `main`, including for the repo owner; commits and PRs visible in a real GitHub repo). Task 6 documents the exact commands as a runbook; running them is a deliberate, separate step the user does after reviewing this plan's output, not something executed autonomously as part of plan execution.
- Match real resource names exactly: ECS cluster `anagrams-cluster` (`aws_ecs_cluster.main`), service `anagrams-api` (`aws_ecs_service.api`), task family `anagrams-api` (`aws_ecs_task_definition.api`), ECR repo `anagrams-api` (`aws_ecr_repository.api`), container name `api` (from `ecs.tf`'s `container_definitions[0].name`), health route `GET /api/health` returning `{"status":"ok"}` (`docker-101/anagrams-2/server/src/index.js:435`), frontend build script `npm run build` and lint script `npm run lint` (`docker-101/anagrams-2/am-client/package.json`), frontend `<title>` marker `Vite + React` (`docker-101/anagrams-2/am-client/index.html`).
- `aws_ecs_service.api.id` is that service's full ARN (confirmed via `terraform state show aws_ecs_service.api` — not `.arn`, which this resource type doesn't export separately).
- IAM role names are literal, not prefixed with `${var.project_name}-` (unlike other resources in this codebase) — the design doc names them exactly `github-actions-api-deploy` and `github-actions-frontend-deploy`.
- All new Terraform code lives in `aws-deploy-demo/terraform/`; all workflow files live in `.github/workflows/` at the repo root (GitHub Actions requires this exact path regardless of monorepo structure).
- GitHub repo variables referenced in workflows via `${{ vars.NAME }}` must exactly match the names Task 6's runbook sets: `AWS_REGION`, `ECR_REPOSITORY_URL`, `ECS_CLUSTER`, `ECS_SERVICE`, `ECS_TASK_FAMILY`, `ALB_DNS_NAME`, `S3_BUCKET`, `CLOUDFRONT_DISTRIBUTION_ID`, `CLOUDFRONT_DOMAIN`, `GITHUB_ACTIONS_API_ROLE_ARN`, `GITHUB_ACTIONS_FRONTEND_ROLE_ARN`.
- No `actionlint` available in this environment; workflow YAML is validated locally with `python3`'s `yaml.safe_load` (PyYAML 6.0.1 confirmed installed) for syntax plus a small assertion script for job-id/trigger correctness. Real correctness (action inputs, IAM permissions) is only provable by actually running the workflow on GitHub — that happens in Task 6's runbook, not as an automated step here.

---

### Task 1: Terraform — GitHub OIDC provider, two deploy roles, new outputs

**Files:**
- Create: `aws-deploy-demo/terraform/github_oidc.tf`
- Modify: `aws-deploy-demo/terraform/outputs.tf`

**Interfaces:**
- Consumes: `aws_ecr_repository.api` (`ecr.tf`), `aws_ecs_service.api` (`ecs_service.tf`), `aws_iam_role.ecs_execution` / `aws_iam_role.ecs_task` (`iam.tf`), `aws_s3_bucket.client` / `aws_cloudfront_distribution.client` (`s3_cloudfront.tf`), `var.aws_region` / `var.project_name` (`variables.tf`) — all pre-existing.
- Produces: Terraform outputs `github_actions_api_role_arn`, `github_actions_frontend_role_arn`, `aws_region`, `ecs_cluster_name`, `ecs_service_name`, `ecs_task_family` — consumed by Task 6's runbook to populate GitHub repo variables. (Outputs `ecr_repository_url`, `alb_dns_name`, `client_bucket_name`, `cloudfront_distribution_id`, `cloudfront_domain_name` already exist and are reused as-is.)

- [ ] **Step 1: Write `github_oidc.tf`**

```hcl
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
```

- [ ] **Step 2: Append new outputs to `outputs.tf`**

Add after the existing `client_bucket_name` output (do not modify any existing output):

```hcl
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
```

- [ ] **Step 3: Format and validate**

Run:
```bash
cd aws-deploy-demo/terraform
terraform fmt -check github_oidc.tf outputs.tf
terraform validate
```
Expected: `fmt -check` prints nothing (files already canonically formatted — if it lists a filename, run `terraform fmt` without `-check` and re-check); `validate` prints `Success! The configuration is valid.`

- [ ] **Step 4: Plan and confirm the change is additive-only**

Run (from `aws-deploy-demo/terraform/`, using the already-configured `nick-link-sandbox` AWS credentials):
```bash
terraform plan -out=/tmp/oidc.tfplan
```
Expected: plan summary reads `Plan: 5 to add, 0 to change, 0 to destroy.` — the 5 new resources are `aws_iam_openid_connect_provider.github`, `aws_iam_role.github_actions_api_deploy`, `aws_iam_role_policy.github_actions_api_deploy`, `aws_iam_role.github_actions_frontend_deploy`, `aws_iam_role_policy.github_actions_frontend_deploy`. No existing resource (ECS service, S3 bucket, CloudFront distribution, RDS instance) appears in the diff. Do **not** run `terraform apply` — that's Task 6.

- [ ] **Step 5: Commit**

```bash
git add aws-deploy-demo/terraform/github_oidc.tf aws-deploy-demo/terraform/outputs.tf
git commit -m "Add GitHub OIDC provider and two least-privilege deploy roles"
```

---

### Task 2: `.github/workflows/validate-api.yml`

**Files:**
- Create: `.github/workflows/validate-api.yml`

**Interfaces:**
- Consumes: nothing (no AWS access, no repo variables).
- Produces: a required-status-check name of `Validate API / build` (job id `build`) — consumed by Task 6's branch protection setup.

- [ ] **Step 1: Write the workflow**

```yaml
name: Validate API

on:
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - id: filter
        uses: dorny/paths-filter@v3
        with:
          filters: |
            server:
              - 'docker-101/anagrams-2/server/**'
              - '.github/workflows/validate-api.yml'

      - name: Build server image
        if: steps.filter.outputs.server == 'true'
        run: docker build -t anagrams-api:pr-check docker-101/anagrams-2/server
```

- [ ] **Step 2: Validate YAML syntax and job id**

Run:
```bash
python3 -c "
import yaml
with open('.github/workflows/validate-api.yml') as f:
    doc = yaml.safe_load(f)
assert True in doc, 'on: trigger missing'
assert list(doc['jobs'].keys()) == ['build'], 'job id must be build'
assert doc[True]['pull_request']['branches'] == ['main']
print('OK: job id =', list(doc['jobs'].keys())[0])
"
```
Expected: `OK: job id = build` (PyYAML parses the YAML `on:` key as the boolean `True`, not the string `'on'` — this is expected and confirms the file parses as valid YAML 1.1).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/validate-api.yml
git commit -m "Add PR-triggered build-only validation workflow for the API"
```

---

### Task 3: `.github/workflows/validate-frontend.yml`

**Files:**
- Create: `.github/workflows/validate-frontend.yml`

**Interfaces:**
- Consumes: nothing (no AWS access, no repo variables).
- Produces: a required-status-check name of `Validate Frontend / build` (job id `build`) — consumed by Task 6's branch protection setup.

- [ ] **Step 1: Write the workflow**

```yaml
name: Validate Frontend

on:
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - id: filter
        uses: dorny/paths-filter@v3
        with:
          filters: |
            client:
              - 'docker-101/anagrams-2/am-client/**'
              - '.github/workflows/validate-frontend.yml'

      - uses: actions/setup-node@v4
        if: steps.filter.outputs.client == 'true'
        with:
          node-version: 20

      - name: Install, lint, build
        if: steps.filter.outputs.client == 'true'
        working-directory: docker-101/anagrams-2/am-client
        run: |
          npm ci
          npm run lint
          npm run build
```

- [ ] **Step 2: Validate YAML syntax and job id**

Run:
```bash
python3 -c "
import yaml
with open('.github/workflows/validate-frontend.yml') as f:
    doc = yaml.safe_load(f)
assert list(doc['jobs'].keys()) == ['build'], 'job id must be build'
assert doc[True]['pull_request']['branches'] == ['main']
print('OK: job id =', list(doc['jobs'].keys())[0])
"
```
Expected: `OK: job id = build`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/validate-frontend.yml
git commit -m "Add PR-triggered build-only validation workflow for the frontend"
```

---

### Task 4: `.github/workflows/deploy-api.yml`

**Files:**
- Create: `.github/workflows/deploy-api.yml`

**Interfaces:**
- Consumes: repo variables `GITHUB_ACTIONS_API_ROLE_ARN`, `AWS_REGION`, `ECR_REPOSITORY_URL`, `ECS_TASK_FAMILY`, `ECS_CLUSTER`, `ECS_SERVICE`, `ALB_DNS_NAME` — set by Task 6's runbook from Task 1's Terraform outputs. Container name `api` (must match `ecs.tf`'s `container_definitions[0].name`).
- Produces: nothing consumed by later tasks in this plan (terminal workflow); pushes images and rolls out the ECS service when run on GitHub.

- [ ] **Step 1: Write the workflow**

```yaml
name: Deploy API

on:
  push:
    branches: [main]
    paths:
      - "docker-101/anagrams-2/server/**"
      - ".github/workflows/deploy-api.yml"

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.GITHUB_ACTIONS_API_ROLE_ARN }}
          aws-region: ${{ vars.AWS_REGION }}

      - uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push image
        working-directory: docker-101/anagrams-2/server
        env:
          ECR_REPOSITORY_URL: ${{ vars.ECR_REPOSITORY_URL }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t "$ECR_REPOSITORY_URL:$IMAGE_TAG" -t "$ECR_REPOSITORY_URL:latest" .
          docker push "$ECR_REPOSITORY_URL:$IMAGE_TAG"
          docker push "$ECR_REPOSITORY_URL:latest"

      - name: Fetch current task definition
        run: |
          aws ecs describe-task-definition \
            --task-definition "${{ vars.ECS_TASK_FAMILY }}" \
            --query "taskDefinition" > task-definition.json

      - name: Render new task definition with the new image
        id: render-task-def
        uses: aws-actions/amazon-ecs-render-task-definition@v1
        with:
          task-definition: task-definition.json
          container-name: api
          image: ${{ vars.ECR_REPOSITORY_URL }}:${{ github.sha }}

      - name: Deploy new task definition to the service
        uses: aws-actions/amazon-ecs-deploy-task-definition@v2
        with:
          task-definition: ${{ steps.render-task-def.outputs.task-definition }}
          cluster: ${{ vars.ECS_CLUSTER }}
          service: ${{ vars.ECS_SERVICE }}
          wait-for-service-stability: true

      - name: Smoke test /api/health
        run: |
          for i in $(seq 1 10); do
            status=$(curl -s -o /dev/null -w "%{http_code}" "${{ vars.ALB_DNS_NAME }}/api/health" || true)
            if [ "$status" = "200" ]; then
              echo "Health check passed on attempt $i"
              exit 0
            fi
            echo "Attempt $i: got status $status, retrying in 10s..."
            sleep 10
          done
          echo "Health check never returned 200 after 10 attempts"
          exit 1
```

- [ ] **Step 2: Validate YAML syntax and trigger/permissions**

Run:
```bash
python3 -c "
import yaml
with open('.github/workflows/deploy-api.yml') as f:
    doc = yaml.safe_load(f)
assert doc[True]['push']['branches'] == ['main']
assert 'docker-101/anagrams-2/server/**' in doc[True]['push']['paths']
assert doc['permissions']['id-token'] == 'write'
print('OK:', list(doc['jobs'].keys()))
"
```
Expected: `OK: ['deploy']`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy-api.yml
git commit -m "Add push-triggered deploy workflow for the API via OIDC"
```

---

### Task 5: `.github/workflows/deploy-frontend.yml`

**Files:**
- Create: `.github/workflows/deploy-frontend.yml`

**Interfaces:**
- Consumes: repo variables `GITHUB_ACTIONS_FRONTEND_ROLE_ARN`, `AWS_REGION`, `S3_BUCKET`, `CLOUDFRONT_DISTRIBUTION_ID`, `CLOUDFRONT_DOMAIN` — set by Task 6's runbook from Task 1's Terraform outputs.
- Produces: nothing consumed by later tasks in this plan (terminal workflow); syncs the built client to S3 and invalidates CloudFront when run on GitHub.

- [ ] **Step 1: Write the workflow**

```yaml
name: Deploy Frontend

on:
  push:
    branches: [main]
    paths:
      - "docker-101/anagrams-2/am-client/**"
      - ".github/workflows/deploy-frontend.yml"

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20

      - name: Install and build
        working-directory: docker-101/anagrams-2/am-client
        env:
          VITE_API_URL: /api
        run: |
          npm ci
          npm run build

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.GITHUB_ACTIONS_FRONTEND_ROLE_ARN }}
          aws-region: ${{ vars.AWS_REGION }}

      - name: Sync build output to S3
        run: |
          aws s3 sync docker-101/anagrams-2/am-client/dist \
            "s3://${{ vars.S3_BUCKET }}" --delete

      - name: Invalidate CloudFront cache
        run: |
          aws cloudfront create-invalidation \
            --distribution-id "${{ vars.CLOUDFRONT_DISTRIBUTION_ID }}" \
            --paths "/*"

      - name: Smoke test CloudFront URL
        run: |
          for i in $(seq 1 10); do
            body=$(curl -s "${{ vars.CLOUDFRONT_DOMAIN }}" || true)
            if echo "$body" | grep -q "<title>Vite + React</title>"; then
              echo "Smoke test passed on attempt $i"
              exit 0
            fi
            echo "Attempt $i: expected marker not found, retrying in 10s..."
            sleep 10
          done
          echo "Smoke test failed: marker never appeared"
          exit 1
```

- [ ] **Step 2: Validate YAML syntax and trigger/permissions**

Run:
```bash
python3 -c "
import yaml
with open('.github/workflows/deploy-frontend.yml') as f:
    doc = yaml.safe_load(f)
assert doc[True]['push']['branches'] == ['main']
assert 'docker-101/anagrams-2/am-client/**' in doc[True]['push']['paths']
assert doc['permissions']['id-token'] == 'write'
print('OK:', list(doc['jobs'].keys()))
"
```
Expected: `OK: ['deploy']`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy-frontend.yml
git commit -m "Add push-triggered deploy workflow for the frontend via OIDC"
```

---

### Task 6: Rollout runbook (documentation only — not executed by this plan)

**Files:**
- Create: `aws-deploy-demo/docs/cicd-rollout-runbook.md`

**Interfaces:**
- Consumes: Task 1's Terraform outputs (`github_actions_api_role_arn`, `github_actions_frontend_role_arn`, `aws_region`, `ecs_cluster_name`, `ecs_service_name`, `ecs_task_family`, plus the pre-existing `ecr_repository_url`, `alb_dns_name`, `client_bucket_name`, `cloudfront_distribution_id`, `cloudfront_domain_name`), and the four workflow files from Tasks 2–5.
- Produces: nothing further — this is the terminal task. Running the commands it documents is a separate, deliberate action taken after this plan is reviewed, per the Global Constraints above.

- [ ] **Step 1: Write the runbook**

```markdown
# CI/CD Rollout Runbook

Ordered, one-time steps to turn on the anagrams CI/CD pipeline built in
`docs/superpowers/plans/2026-07-10-anagrams-cicd-implementation.md`. Each
step is a real, mostly-irreversible action against the live AWS account
(798294347421) and the `nz3424/ai-work-prep` GitHub repo — run them
yourself, in order, confirming each one worked before moving to the next.

## 1. Apply the Terraform

\`\`\`bash
cd aws-deploy-demo/terraform
terraform apply /tmp/oidc.tfplan   # or re-run `terraform plan` first if stale
\`\`\`
Confirm: `Apply complete! Resources: 5 added, 0 changed, 0 destroyed.`

## 2. Populate GitHub repo variables

\`\`\`bash
cd aws-deploy-demo/terraform
REPO=nz3424/ai-work-prep

gh variable set AWS_REGION --repo "$REPO" --body "$(terraform output -raw aws_region)"
gh variable set ECR_REPOSITORY_URL --repo "$REPO" --body "$(terraform output -raw ecr_repository_url)"
gh variable set ECS_CLUSTER --repo "$REPO" --body "$(terraform output -raw ecs_cluster_name)"
gh variable set ECS_SERVICE --repo "$REPO" --body "$(terraform output -raw ecs_service_name)"
gh variable set ECS_TASK_FAMILY --repo "$REPO" --body "$(terraform output -raw ecs_task_family)"
gh variable set ALB_DNS_NAME --repo "$REPO" --body "$(terraform output -raw alb_dns_name)"
gh variable set S3_BUCKET --repo "$REPO" --body "$(terraform output -raw client_bucket_name)"
gh variable set CLOUDFRONT_DISTRIBUTION_ID --repo "$REPO" --body "$(terraform output -raw cloudfront_distribution_id)"
gh variable set CLOUDFRONT_DOMAIN --repo "$REPO" --body "$(terraform output -raw cloudfront_domain_name)"
gh variable set GITHUB_ACTIONS_API_ROLE_ARN --repo "$REPO" --body "$(terraform output -raw github_actions_api_role_arn)"
gh variable set GITHUB_ACTIONS_FRONTEND_ROLE_ARN --repo "$REPO" --body "$(terraform output -raw github_actions_frontend_role_arn)"

gh variable list --repo "$REPO"
\`\`\`
Confirm: all 11 variables listed with non-empty values.

## 3. Push the four workflow files to `main`

This is the last direct push `main` will ever accept — branch protection
goes on in step 5.

\`\`\`bash
git push origin main
\`\`\`
Confirm: `git log --oneline -6` on GitHub shows the workflow commits, and
Actions tab shows no unexpected run (deploy workflows are path-filtered;
pushing workflow files alone shouldn't trigger them unless this push also
touches `server/**` or `am-client/**`).

## 4. Open a throwaway PR to register the required-check names

\`\`\`bash
git checkout -b throwaway-check-registration
echo "<!-- throwaway PR to register status check names -->" >> README.md
git add README.md
git commit -m "Throwaway change to register CI check names"
git push origin throwaway-check-registration
gh pr create --repo nz3424/ai-work-prep --title "Throwaway: register CI checks" \
  --body "Registers Validate API / build and Validate Frontend / build as check names so they become selectable in branch protection. Touches neither server/** nor am-client/**, so both checks should skip real work and report success quickly." \
  --base main
\`\`\`
Confirm: both `Validate API / build` and `Validate Frontend / build` appear
on the PR and go green within ~30s (skip-logic path, no real build).
Merge the PR, then delete the branch:
\`\`\`bash
gh pr merge --repo nz3424/ai-work-prep --squash --delete-branch
\`\`\`

## 5. Enable branch protection on `main`

\`\`\`bash
cat <<'EOF' > /tmp/branch-protection.json
{
  "required_status_checks": {
    "strict": false,
    "checks": [
      { "context": "Validate API / build" },
      { "context": "Validate Frontend / build" }
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF

gh api --method PUT repos/nz3424/ai-work-prep/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  --input /tmp/branch-protection.json

gh api repos/nz3424/ai-work-prep/branches/main/protection
\`\`\`
Confirm the GET echoes back `enforce_admins.enabled: true` and both checks
listed. Then confirm a direct push is rejected:
\`\`\`bash
echo "test" >> README.md && git commit -am "test direct push" && git push origin main
\`\`\`
Expected: rejected with a protected-branch error. Revert the local test
commit (`git reset --hard HEAD~1`) since it never reached GitHub.

## 6. End-to-end test: API change through the full pipeline

\`\`\`bash
git checkout -b test-api-pipeline
# edit docker-101/anagrams-2/server/src/index.js:436 — tweak the health
# response, e.g. res.json({ status: "ok", version: "1" });
git commit -am "Test: tweak health response for CI/CD pipeline verification"
git push origin test-api-pipeline
gh pr create --repo nz3424/ai-work-prep --base main --title "Test API pipeline" --body "Verifies validate-api.yml and deploy-api.yml end-to-end."
\`\`\`
Confirm: `Validate API / build` runs and goes green (real docker build this
time), `Validate Frontend / build` skips and goes green fast. Merge the PR;
confirm `deploy-api.yml` runs in the Actions tab and succeeds (image
pushed, task def revision bumped, service stable, smoke test green). Then:
\`\`\`bash
curl "$(cd aws-deploy-demo/terraform && terraform output -raw alb_dns_name)/api/health"
\`\`\`
Confirm the response reflects the change (e.g. includes `"version":"1"`).

## 7. End-to-end test: frontend change through the full pipeline

Same pattern as step 6 — a small visible text change under
`docker-101/anagrams-2/am-client/src/`, on a branch, opened as a PR.
Confirm `Validate Frontend / build` runs for real (lint + build) and goes
green, `deploy-frontend.yml` runs after merge, and:
\`\`\`bash
curl "$(cd aws-deploy-demo/terraform && terraform output -raw cloudfront_domain_name)"
\`\`\`
shows the change.

## 8. Confirm unrelated subprojects aren't blocked

\`\`\`bash
git checkout -b test-unrelated-pr main
echo "<!-- throwaway -->" >> eval-harness/README.md
git commit -am "Test: confirm anagrams checks don't block unrelated PRs"
git push origin test-unrelated-pr
gh pr create --repo nz3424/ai-work-prep --base main --title "Test unrelated PR" --body "Confirms an eval-harness-only PR isn't blocked by the anagrams required checks."
\`\`\`
Confirm both `Validate API / build` and `Validate Frontend / build` report
success within ~30s (skip path) and the PR merges normally with neither
deploy workflow firing. Delete the test branch after merging.
```

- [ ] **Step 2: Confirm the file is well-formed markdown**

Run:
```bash
python3 -c "
with open('aws-deploy-demo/docs/cicd-rollout-runbook.md') as f:
    content = f.read()
assert content.startswith('# CI/CD Rollout Runbook')
assert content.count('\`\`\`') % 2 == 0, 'unbalanced code fences'
print('OK: balanced fences, length', len(content))
"
```
Expected: `OK: balanced fences, length <some number>`

- [ ] **Step 3: Commit**

```bash
git add aws-deploy-demo/docs/cicd-rollout-runbook.md
git commit -m "Add CI/CD rollout runbook documenting the manual go-live steps"
```

---

## Self-Review Notes

- **Spec coverage:** OIDC provider + two scoped IAM roles (Task 1) · four workflows matching the design doc's architecture diagram exactly, including the always-triggers-but-skips pattern for validate workflows and path-filtered triggers for deploy workflows (Tasks 2–5) · repo variable population, direct-push-then-protect sequencing, throwaway PR for check-name registration, branch protection payload, and the full 7-point verification sequence from the design doc's "Verification" section (Task 6). Out-of-scope items (canary/blue-green, multi-region, custom domain, rollback automation, other subprojects' CI) are correctly not built.
- **No placeholders:** every workflow step has real commands/actions; the runbook has real `gh`/`terraform`/`curl` commands, not "TBD" instructions.
- **Type/name consistency checked:** repo variable names in Task 4/5 workflows (`${{ vars.X }}`) match Task 6's `gh variable set X` calls exactly; Terraform output names in Task 1 match the `terraform output -raw <name>` calls in Task 6; container name `api` in Task 4's render-task-definition step matches `ecs.tf`'s existing `container_definitions[0].name`; job id `build` in Tasks 2–3 matches the required-check names (`Validate API / build`, `Validate Frontend / build`) referenced in Task 6's branch protection JSON.
