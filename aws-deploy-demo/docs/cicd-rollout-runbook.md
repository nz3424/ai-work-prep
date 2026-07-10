# CI/CD Rollout Runbook

Ordered, one-time steps to turn on the anagrams CI/CD pipeline built in
`docs/superpowers/plans/2026-07-10-anagrams-cicd-implementation.md`. Each
step is a real, mostly-irreversible action against the live AWS account
(798294347421) and the `nz3424/ai-work-prep` GitHub repo — run them
yourself, in order, confirming each one worked before moving to the next.

## 1. Apply the Terraform

```bash
cd aws-deploy-demo/terraform
terraform apply /tmp/oidc.tfplan   # or re-run `terraform plan` first if stale
```
Confirm: `Apply complete! Resources: 5 added, 0 changed, 0 destroyed.`

If this fails with `EntityAlreadyExists` on the OIDC provider, an
identity provider for `token.actions.githubusercontent.com` already
exists in this account outside Terraform's state — import it instead of
recreating it:
```bash
terraform import aws_iam_openid_connect_provider.github \
  "arn:aws:iam::798294347421:oidc-provider/token.actions.githubusercontent.com"
```
then re-run `terraform apply`.

## 2. Populate GitHub repo variables

GitHub rejects any repo variable name starting with `GITHUB_` (reserved
for its own built-in variables) — that's why the two role ARNs below are
named `ACTIONS_API_ROLE_ARN` / `ACTIONS_FRONTEND_ROLE_ARN`, not
`GITHUB_ACTIONS_*_ROLE_ARN`.

```bash
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
gh variable set ACTIONS_API_ROLE_ARN --repo "$REPO" --body "$(terraform output -raw github_actions_api_role_arn)"
gh variable set ACTIONS_FRONTEND_ROLE_ARN --repo "$REPO" --body "$(terraform output -raw github_actions_frontend_role_arn)"

gh variable list --repo "$REPO"
```
Confirm: all 11 variables listed with non-empty values.

## 3. Confirm the four workflow files are on `main`

This repo already has a GitHub ruleset requiring all changes to `main`
go through a pull request — direct `git push origin main` is rejected
regardless of whether Terraform-managed branch protection (step 5) is
on yet. The four workflow files merged to `main` via a PR already, so
there's nothing to push here; just confirm they're present:

```bash
git log --oneline -6 origin/main -- .github/workflows/
```
Confirm: `validate-api.yml`, `validate-frontend.yml`, `deploy-api.yml`,
and `deploy-frontend.yml` all show up, and the Actions tab shows no
unexpected run from that merge (deploy workflows are path-filtered;
merging workflow files alone shouldn't trigger them unless that merge
also touched `server/**` or `am-client/**`).

## 4. Open a throwaway PR to register the required-check names

```bash
git checkout -b throwaway-check-registration
echo "<!-- throwaway PR to register status check names -->" >> README.md
git add README.md
git commit -m "Throwaway change to register CI check names"
git push origin throwaway-check-registration
gh pr create --repo nz3424/ai-work-prep --title "Throwaway: register CI checks" \
  --body "Registers Validate API / build and Validate Frontend / build as check names so they become selectable in branch protection. Touches neither server/** nor am-client/**, so both checks should skip real work and report success quickly." \
  --base main
```
Confirm: both `Validate API / build` and `Validate Frontend / build` appear
on the PR and go green within ~30s (skip-logic path, no real build).
Merge the PR, then delete the branch:
```bash
gh pr merge --repo nz3424/ai-work-prep --squash --delete-branch
```

## 5. Enable branch protection on `main`

```bash
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
```
Confirm the GET echoes back `enforce_admins.enabled: true` and both checks
listed. Then confirm a direct push is rejected:
```bash
echo "test" >> README.md && git commit -am "test direct push" && git push origin main
```
Expected: rejected with a protected-branch error. Revert the local test
commit (`git reset --hard HEAD~1`) since it never reached GitHub.

## 6. End-to-end test: API change through the full pipeline

```bash
git checkout -b test-api-pipeline
# edit docker-101/anagrams-2/server/src/index.js:436 — tweak the health
# response, e.g. res.json({ status: "ok", version: "1" });
git commit -am "Test: tweak health response for CI/CD pipeline verification"
git push origin test-api-pipeline
gh pr create --repo nz3424/ai-work-prep --base main --title "Test API pipeline" --body "Verifies validate-api.yml and deploy-api.yml end-to-end."
```
Confirm: `Validate API / build` runs and goes green (real docker build this
time), `Validate Frontend / build` skips and goes green fast. Merge the PR;
confirm `deploy-api.yml` runs in the Actions tab and succeeds (image
pushed, task def revision bumped, service stable, smoke test green). Then:
```bash
curl "$(cd aws-deploy-demo/terraform && terraform output -raw alb_dns_name)/api/health"
```
Confirm the response reflects the change (e.g. includes `"version":"1"`).

## 7. End-to-end test: frontend change through the full pipeline

Same pattern as step 6 — a small visible text change under
`docker-101/anagrams-2/am-client/src/`, on a branch, opened as a PR.
Confirm `Validate Frontend / build` runs for real (lint + build) and goes
green, `deploy-frontend.yml` runs after merge, and:
```bash
curl "$(cd aws-deploy-demo/terraform && terraform output -raw cloudfront_domain_name)"
```
shows the change.

## 8. Confirm unrelated subprojects aren't blocked

```bash
git checkout -b test-unrelated-pr main
echo "<!-- throwaway -->" >> eval-harness/README.md
git commit -am "Test: confirm anagrams checks don't block unrelated PRs"
git push origin test-unrelated-pr
gh pr create --repo nz3424/ai-work-prep --base main --title "Test unrelated PR" --body "Confirms an eval-harness-only PR isn't blocked by the anagrams required checks."
```
Confirm both `Validate API / build` and `Validate Frontend / build` report
success within ~30s (skip path) and the PR merges normally with neither
deploy workflow firing. Delete the test branch after merging.
