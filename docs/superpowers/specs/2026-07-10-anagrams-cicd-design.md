# Anagrams CI/CD Pipeline — Design

**Date:** 2026-07-10
**Status:** Approved for implementation planning
**Repo slot:** `aws-deploy-demo/` (Track 1, Day 3) — the "stretch: wire up basic CI"
item from `aws-deploy-demo/README.md`.

## Context

Both halves of `docker-101/anagrams-2` are live on AWS via manually-run Terraform and
manual deploy steps:

- **API** — Express server, containerized, running on ECS Fargate behind an ALB. Image
  lives in ECR, currently pushed by hand and always tagged `:latest`
  (`aws-deploy-demo/terraform/ecs.tf` hardcodes `image = "...:latest"` in the task
  definition).
- **Frontend** (`am-client`) — React/Vite static build, deployed via
  `npm run build` → `aws s3 sync` → CloudFront invalidation, all run by hand (see
  `docs/superpowers/specs/2026-07-09-s3-cloudfront-frontend-design.md`).

Neither has a smoke test after deploy, and there is no CI. This spec adds two GitHub
Actions workflows — one per deployable — that build, deploy, and smoke-test on every
push to `main` that touches the relevant subtree. The repo (`nz3424/ai-work-prep`,
containing several unrelated subprojects — `eval-harness`, `hermes-assistant`,
`agent-capstone` — alongside `docker-101`/`aws-deploy-demo`) already pushes straight to
`main`; this spec does not introduce a PR-gated flow, since there's no existing PR habit
to hang one on.

## Explicit scope decisions

- **Both API and frontend get workflows.** Both are already deployed; leaving either
  manual would just move the "stretch goal" gap rather than close it.
- **Auth: GitHub OIDC + IAM roles, not static access keys.** A prior session's handoff
  doc (`aws-deploy-demo/docs/handoff.md`) flagged that `aws configure list` output —
  possibly including real credentials — was pasted into a chat transcript, and
  recommended avoiding long-lived keys going forward. OIDC means no AWS credential ever
  exists at rest in GitHub; a short-lived token is exchanged per workflow run.
- **Two IAM roles, not one.** `github-actions-api-deploy` (ECR push, ECS
  register/update, scoped `iam:PassRole` on only the two existing ECS roles) and
  `github-actions-frontend-deploy` (S3 sync on the client bucket, CloudFront
  invalidation) are separate, least-privilege roles sharing one OIDC provider. A bug or
  compromise in one workflow can't reach the other's resources.
- **Trigger: push to `main`, path-filtered per workflow.** `deploy-api.yml` only fires
  on changes under `docker-101/anagrams-2/server/**` (+ itself); `deploy-frontend.yml`
  only on `docker-101/anagrams-2/am-client/**` (+ itself). Prevents unrelated commits
  elsewhere in the monorepo from triggering AWS deploys.
- **API image tagging: git SHA, not just `:latest`.** Each push builds and pushes
  `:<git-sha>` (plus `:latest` for convenience), registers a new ECS task definition
  revision pointing at the SHA tag, and updates the service to that revision. Gives
  per-commit traceability (which commit is actually running) and a clean rollback path
  (redeploy an older task def revision) that `:latest` alone doesn't.
- **Smoke tests included in both workflows**, closing out the smoke-test item the
  frontend handoff doc left undone. API: curl the ALB's `/api/health` endpoint. Frontend:
  curl the CloudFront URL. Both retry briefly (deploys aren't instantaneous) and fail the
  workflow loudly on a non-200 or missing expected content, rather than reporting
  "deployed" when the thing that got deployed is actually broken.
- **Config as GitHub repo variables, not secrets.** Region, cluster/service/family
  names, bucket name, distribution ID, role ARNs — all Terraform outputs, none of them
  sensitive. Secrets are reserved for things that actually need to be secret (there
  currently are none needed, since OIDC replaces static keys).
- **Out of scope:** PR-gated builds, canary/blue-green rollout strategies, multi-region,
  a custom domain (unchanged from the frontend spec), rollback automation beyond "redeploy
  an older task def revision by hand."

## Architecture

```
push to main (path-filtered)
        │
        ├─ server/** changed ──► deploy-api.yml
        │                          1. assume github-actions-api-deploy (OIDC)
        │                          2. docker build, push :sha + :latest to ECR
        │                          3. render + register new task def revision
        │                          4. ecs update-service, wait for stability
        │                          5. smoke test: curl ALB /api/health
        │
        └─ am-client/** changed ► deploy-frontend.yml
                                   1. npm ci && npm run build
                                   2. assume github-actions-frontend-deploy (OIDC)
                                   3. aws s3 sync dist/ → bucket --delete
                                   4. cloudfront create-invalidation /*
                                   5. smoke test: curl CloudFront URL
```

## AWS changes (Terraform, `aws-deploy-demo/terraform/`)

New file, e.g. `github_oidc.tf`:

- `aws_iam_openid_connect_provider` for `token.actions.githubusercontent.com`
  (`client_id_list = ["sts.amazonaws.com"]`), shared by both roles.
- `aws_iam_role.github_actions_api_deploy` — trust policy conditioned on
  `repo:nz3424/ai-work-prep:ref:refs/heads/main` via the OIDC provider's `sub` claim.
  Inline/attached policy: `ecr:GetAuthorizationToken` (`Resource: *`, required by the
  API); `ecr:BatchCheckLayerAvailability`, `PutImage`, `InitiateLayerUpload`,
  `UploadLayerPart`, `CompleteLayerUpload`, `GetDownloadUrlForLayer` scoped to the
  `anagrams-api` repo ARN; `ecs:RegisterTaskDefinition`, `DescribeTaskDefinition`
  (`Resource: *`, required by the API); `ecs:UpdateService`, `DescribeServices` scoped
  to the `anagrams-api` service ARN; `iam:PassRole` scoped to exactly
  `aws_iam_role.ecs_execution.arn` and `aws_iam_role.ecs_task.arn`.
- `aws_iam_role.github_actions_frontend_deploy` — same trust condition. Policy:
  `s3:PutObject`, `DeleteObject`, `ListBucket` scoped to the client bucket + its
  objects; `cloudfront:CreateInvalidation`, `GetInvalidation` scoped to the client
  distribution ARN.
- New outputs: both role ARNs, plus re-exposing existing values needed as workflow
  inputs (ECR repo URL, ECS cluster/service/family names, ALB DNS name — most already
  exist in `outputs.tf`).

## GitHub Actions workflows

**`.github/workflows/deploy-api.yml`**

```yaml
on:
  push:
    branches: [main]
    paths:
      - "docker-101/anagrams-2/server/**"
      - ".github/workflows/deploy-api.yml"
permissions:
  id-token: write
  contents: read
```

Steps: checkout → `aws-actions/configure-aws-credentials@v4` (role from repo var) →
`aws-actions/amazon-ecr-login@v2` → `docker build` (context
`docker-101/anagrams-2/server`) tagged `:${{ github.sha }}` and `:latest`, push both →
fetch current task def (`aws ecs describe-task-definition`), swap the image field to the
new SHA tag → `aws-actions/amazon-ecs-render-task-definition@v1` +
`aws-actions/amazon-ecs-deploy-task-definition@v2` (`wait-for-service-stability: true`)
→ smoke test step: loop curling `http://<alb_dns>/api/health`, up to ~10 attempts with a
short sleep, fail the job if none return 200.

**`.github/workflows/deploy-frontend.yml`**

```yaml
on:
  push:
    branches: [main]
    paths:
      - "docker-101/anagrams-2/am-client/**"
      - ".github/workflows/deploy-frontend.yml"
permissions:
  id-token: write
  contents: read
```

Steps: checkout → `actions/setup-node@v4` → `npm ci` + `npm run build` in `am-client`
(with `VITE_API_URL=/api`, matching the existing production build config) →
`aws-actions/configure-aws-credentials@v4` (frontend role) → `aws s3 sync dist/
s3://<bucket> --delete` → `aws cloudfront create-invalidation --distribution-id <id>
--paths "/*"` → smoke test step: curl the CloudFront URL, retry briefly, fail on
non-200 or missing expected marker (e.g. the app's `<title>` string).

## Repo configuration

GitHub repo variables (Settings → Actions → Variables), populated from `terraform
output` after `apply`: `AWS_REGION`, `ECR_REPOSITORY_URL`, `ECS_CLUSTER`,
`ECS_SERVICE`, `ECS_TASK_FAMILY`, `ALB_DNS_NAME`, `S3_BUCKET`,
`CLOUDFRONT_DISTRIBUTION_ID`, `CLOUDFRONT_DOMAIN`, `GITHUB_ACTIONS_API_ROLE_ARN`,
`GITHUB_ACTIONS_FRONTEND_ROLE_ARN`. None are secret values.

## Verification

1. `terraform plan`/`apply` the new OIDC provider + two roles; confirm via `terraform
   plan` that no existing resource (ECS service, S3 bucket, CloudFront distribution) is
   touched — this change is additive only.
2. Populate the GitHub repo variables from `terraform output`.
3. Push both workflow files; confirm they don't fire on unrelated paths (e.g. push a
   change under `eval-harness/` and confirm neither workflow runs).
4. Make one trivial change to validate each pipeline end-to-end — e.g. a copy tweak in
   the API's `/api/health` response and a small text change in the frontend UI — push to
   `main`, watch the corresponding Action run, and confirm: the workflow succeeds, the
   smoke test passes, and the change is actually visible at the live ALB/CloudFront URLs
   afterward.

## Out of scope

- PR-gated builds (build-only on PR, deploy-only on merge).
- Canary/blue-green deploys, multi-region, custom domain.
- Automated rollback (beyond the manual "redeploy an older ECS task def revision"
  path that SHA-tagging enables).
- Any change to `terraform.tfvars` handling or the credential-rotation follow-up noted
  in `aws-deploy-demo/docs/handoff.md` (separate concern from this spec).
