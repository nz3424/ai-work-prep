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

Neither has a smoke test after deploy, and there is no CI. This spec adds four GitHub
Actions workflows — a build-only validation workflow and a deploy workflow, per
deployable — plus branch protection on `main` requiring a PR with passing checks
before merge. The explicit goal (Nick's framing) is to mirror how production repos
actually work: changes land via PR, a build must succeed before that PR can merge, and
only then does it reach `main` / prod. This repo (`nz3424/ai-work-prep`) also contains
several unrelated subprojects — `eval-harness`, `hermes-assistant`, `agent-capstone` —
that don't yet have their own CI. Branch protection is a GitHub setting on the branch,
not scopable by path, so once enabled it applies to *every* push to `main`, not just
anagrams changes. See "Branch protection" below for how the validation workflows are
built so this doesn't deadlock or block unrelated subprojects' PRs.

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
- **Deploy trigger: push to `main`, path-filtered per workflow.** `deploy-api.yml`
  only fires on changes under `docker-101/anagrams-2/server/**` (+ itself);
  `deploy-frontend.yml` only on `docker-101/anagrams-2/am-client/**` (+ itself).
  Prevents unrelated commits elsewhere in the monorepo from triggering AWS deploys.
- **PR validation workflows, build-only, no AWS access.** `validate-api.yml` and
  `validate-frontend.yml` trigger on *every* `pull_request` targeting `main` — no path
  filter on the trigger itself. Internally, a path-filter step decides whether the
  PR actually touches the relevant subtree; if not, the job completes immediately
  without building anything. If it does, the job builds the Docker image / runs
  `npm run build` + lint. Neither ever touches AWS — no OIDC role assumption, no
  credentials requested. This is deliberately different from the deploy workflows
  (which do keep trigger-level path filters — see below) because these two become
  *required* status checks (see "Branch protection"): a required check that only
  triggers on matching paths would leave non-matching PRs (e.g. an eval-harness-only
  PR) waiting forever on a check that never reports, permanently blocking merge.
  Always-triggering-but-conditionally-skipping avoids that.
- **Deploy workflows keep trigger-level path filters**, unchanged — `deploy-api.yml`
  only runs for `server/**` changes, `deploy-frontend.yml` only for `am-client/**`.
  They are not required checks, so there's no deadlock risk, and skipping the workflow
  entirely (vs. running a no-op job) is simpler when nothing downstream depends on it
  reporting.
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
- **Branch protection on `main`: PR required, checks required, no admin bypass, no
  required approvals.** "Require a pull request before merging" (disallows direct
  pushes to `main`, including from the repo owner) + "Require status checks to pass"
  listing `Validate API / build` and `Validate Frontend / build` + "Do not allow
  bypassing the above settings" (applies to admins too — the whole point is mirroring
  a real gate, not a suggestion). Required-approval count stays at 0: there's no second
  contributor to review PRs, so requiring an approval would just block merges with no
  one able to give one.
- **Out of scope:** canary/blue-green rollout strategies, multi-region, a custom domain
  (unchanged from the frontend spec), rollback automation beyond "redeploy an older task
  def revision by hand," CI for the repo's other subprojects (eval-harness,
  hermes-assistant, agent-capstone) — noted as likely future work, not built here.

## Architecture

```
pull_request → main (every PR, any path)     push to main (merge commit or, since
        │                                     PRs are required, only ever a merge)
        ├─ validate-api.yml                           │
        │    1. path-filter step: does this PR         ├─ server/** ──► deploy-api.yml
        │       touch server/**?                       │                 1. assume github-actions-api-deploy (OIDC)
        │    2. if yes: docker build (no push)          │                 2. docker build, push :sha + :latest to ECR
        │       if no: skip, report success fast        │                 3. render + register new task def revision
        │    3. no AWS access either way                │                 4. ecs update-service, wait for stability
        │                                                │                 5. smoke test: curl ALB /api/health
        └─ validate-frontend.yml                        │
             1. path-filter step: touches am-client/**? └─ am-client/** ► deploy-frontend.yml
             2. if yes: npm ci, build, lint                               1. npm ci && npm run build
                if no: skip, report success fast                          2. assume github-actions-frontend-deploy (OIDC)
             3. no AWS access either way                                  3. aws s3 sync dist/ → bucket --delete
                                                                            4. cloudfront create-invalidation /*
                                                                            5. smoke test: curl CloudFront URL
```

Both `validate-*` checks are marked required in branch protection, so they run (and
must pass) on *every* PR to `main` regardless of what it touches — but for a PR that
doesn't touch `server/**` or `am-client/**`, the real build work is skipped and the
check reports green in seconds. The deploy workflows stay path-filtered at the trigger
level and only run for actual anagrams changes, whether the push came from a merge or
(pre-branch-protection, historically) directly.

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

**`.github/workflows/validate-api.yml`** — job id `build` (so the required-check name
is `Validate API / build`)

```yaml
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

No path filter on `on.pull_request` — it always runs. The `dorny/paths-filter` step
checks out cheaply and sets `steps.filter.outputs.server`; the actual `docker build`
step only runs `if` that's true. For a PR that doesn't touch `server/**`, the job has
one skipped step and reports success in a few seconds — not a real check of anything,
but a fast, always-present status the branch protection rule can rely on. For a PR that
does touch it, a failing build (bad Dockerfile, broken `npm ci`) fails the check;
nothing is deployed either way (this workflow never has AWS credentials).

**`.github/workflows/validate-frontend.yml`** — job id `build` (required-check name
`Validate Frontend / build`)

```yaml
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

Same pattern: always triggers, skips the real work for non-matching PRs, no AWS
credentials requested either way.

## Branch protection (GitHub repo settings, not Terraform)

On `main`, under Settings → Branches → branch protection rule:
- **Require a pull request before merging.** No direct pushes to `main` for anyone,
  including the repo owner — matches "changes go through PRs like real prod."
- **Require status checks to pass before merging**, with `Validate API / build` and
  `Validate Frontend / build` selected as required. (These names only become
  selectable in the GitHub UI after each workflow has run at least once — so the first
  PR after adding the workflow files won't have anything to select from yet; add the
  requirement once both have a run to point at.)
- **Do not allow bypassing the above settings** (no admin exemption).
- Required approving review count: **0** — no second contributor exists to approve.
- "Require branches to be up to date before merging": left off. Not needed for a
  single-contributor repo and would just force redundant re-runs on rebase.

This is a manual GitHub Settings change (branch protection isn't Terraform-managed
here), done once during implementation, after the four workflow files exist and have
each run successfully at least once.

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
3. Push all four workflow files directly to `main` (last direct push this repo will
   ever take — branch protection goes on next). Confirm the deploy workflows don't
   fire on unrelated paths.
4. Open one throwaway PR (any tiny diff) so `validate-api.yml` and
   `validate-frontend.yml` each run at least once — required for their check names to
   become selectable in the branch protection UI. Confirm both report success quickly
   even though the throwaway diff likely touches neither `server/**` nor
   `am-client/**` (proving the skip-logic works before it's load-bearing).
5. Enable branch protection on `main` per the "Branch protection" section above.
   Confirm a direct `git push` to `main` is now rejected.
6. Make one trivial change to validate each pipeline end-to-end — e.g. a copy tweak in
   the API's `/api/health` response — on a branch, opened as a PR:
   - Confirm `validate-api.yml` runs against the PR and its result shows in the PR's
     checks box (the "checks passed" UI), and that merging is blocked until it's
     green.
   - Merge the PR into `main`; confirm `deploy-api.yml` then runs, visible in the
     Actions tab, and that it succeeds: image pushed, task def revision bumped,
     service updated, smoke test green.
   - Curl the live ALB URL to confirm the change is actually there.
   - Repeat the same PR → merge → Actions-tab-run → live-check sequence for a small
     frontend text change, confirming `validate-frontend.yml` then `deploy-frontend.yml`.
7. Confirm an eval-harness-only PR (a trivial, throwaway diff under `eval-harness/`)
   still merges normally — both anagrams checks report success quickly without
   building anything, and neither deploy workflow fires.

## Out of scope

See the "Out of scope" bullet under "Explicit scope decisions" above. Additionally:

- Any change to `terraform.tfvars` handling or the credential-rotation follow-up noted
  in `aws-deploy-demo/docs/handoff.md` (separate concern from this spec).
