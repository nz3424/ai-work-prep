# Cost Pause & Resume Runbook (anagrams demo)

Purpose: this records how the anagrams AWS stack was paused to stop accruing
costs on 2026-07-21, and the exact steps to bring it back. Read this in full
before running `terraform apply` — a naive apply has two gotchas (below).

All terraform commands run from `aws-deploy-demo/terraform/` **on the main
checkout** (the `.tfstate` lives here, not in any git worktree).

## What was done to pause it

1. **ECS service scaled to 0** (via AWS CLI, out-of-band from Terraform):
   `aws ecs update-service --cluster anagrams-cluster --service anagrams-api --desired-count 0`
2. **RDS stopped** (via AWS CLI):
   `aws rds stop-db-instance --db-instance-identifier anagrams-db`
   Note: AWS auto-restarts a stopped RDS instance after 7 days.
3. **Decoupled CloudFront from the ALB in config** so the ALB could be torn
   down without also destroying the CloudFront distribution. In
   `terraform/s3_cloudfront.tf`, the `alb-api` origin's `domain_name` was
   changed from `aws_lb.main.dns_name` to the hardcoded literal
   `"anagrams-alb-903958801.us-east-1.elb.amazonaws.com"`. (This is the current
   uncommitted diff on `s3_cloudfront.tf`.)
4. **State surgery** to clear stale *state-level* dependencies on `aws_lb.main`
   (the config edit alone didn't remove them; they were baked into tfstate).
   Each was `terraform state rm` then `terraform import` — no real AWS change:
   - `aws_cloudfront_distribution.client`  → import ID `ER0MBQQQY1J18`
   - `aws_iam_role_policy.github_actions_frontend_deploy` → import ID `github-actions-frontend-deploy:github-actions-frontend-deploy-policy`
   - `aws_s3_bucket_policy.client` → import ID `anagrams-client-146e2249`
5. **Destroyed the ALB/ECS compute** (the cost driver) with a targeted destroy:
   ```
   terraform destroy \
     -target=aws_lb_listener.http \
     -target=aws_ecs_service.api \
     -target=aws_lb.main \
     -target=aws_lb_target_group.api
   ```
   This plan hits **5** resources, not 4 — it also removes
   `aws_iam_role_policy.github_actions_api_deploy`, which only grants deploy
   permission to the (now-gone) ECS service. That's expected and it comes back
   on apply.

## What is still up (intentionally left running)

- CloudFront distribution `ER0MBQQQY1J18` (domain `d25e8w55y8030q.cloudfront.net`)
  — pay-per-request, ~$0 while idle. Static frontend still served from S3.
  `/api/*` requests return 502 until the ALB is back.
- S3 client bucket `anagrams-client-146e2249` (storage cents).
- RDS `anagrams-db` — **stopped**, not deleted. Data intact. Storage still bills
  (small). Compute charges paused.
- VPC, subnets, security groups, ECR repo, secrets, IAM roles — all free/near-free.

## How to resume (bring the API back)

1. **Revert the CloudFront origin edit** in `terraform/s3_cloudfront.tf`: change
   the `alb-api` origin's `domain_name` back to `aws_lb.main.dns_name` (remove
   the hardcoded literal + the explanatory comment). This must be done BEFORE
   apply so CloudFront re-points at the freshly-created ALB.
2. **Start RDS** if it's still stopped (skip if >7 days elapsed and AWS already
   restarted it):
   `aws rds start-db-instance --db-instance-identifier anagrams-db`
   Wait for status `available` before the app will connect.
3. **Apply**:
   `terraform apply`
   This recreates the ALB, listener, target group, ECS service, and the
   `github_actions_api_deploy` IAM policy, then updates CloudFront to the new
   ALB DNS name (CloudFront update takes ~10-15 min).

## Two gotchas a bare `terraform apply` will hit

Both predate the pause and are unrelated to it, but apply will act on them:

1. **`desired_count` 0 → 1**: apply resets the service to 1 running task. This
   is almost certainly what you want on resume (it undoes the CLI scale-to-0).
2. **`task_definition` :3 → :1**: apply wants to roll the ECS service back to
   task definition revision **:1**, but the last deployed revision was **:3**
   (GitHub Actions registers new revisions outside Terraform, and the service
   has no `lifecycle { ignore_changes = [task_definition] }`). A blind apply
   **rolls the app image back to an older build.** Before applying, decide:
   - re-run the GitHub Actions deploy after apply to push the current image, or
   - add `ignore_changes = [task_definition]` to `aws_ecs_service.api` so
     Terraform stops fighting CI over it (recommended long-term fix), or
   - accept the rollback if :1 is fine for a demo.

## New ALB DNS after resume

The recreated ALB gets a **new** `dns_name` (the old
`anagrams-alb-903958801...` is gone for good). Because step 1 reverts CloudFront
to reference `aws_lb.main.dns_name`, the same apply wires CloudFront to the new
name automatically — no manual DNS update needed. The CloudFront public domain
(`d25e8w55y8030q.cloudfront.net`) does NOT change, since CloudFront itself was
never destroyed.
