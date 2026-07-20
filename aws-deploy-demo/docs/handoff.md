# Handoff: am-client S3 + CloudFront Frontend Deploy

## Status
In progress. Terraform scaffolding for the S3 + CloudFront static frontend deploy is drafted; two follow-up items remain before this is done.

## What's been done
- Design spec committed: `aws-deploy-demo/docs/design-spec.md` (commit `e66500c`, "Add design spec for am-client S3 + CloudFront frontend deploy"). Read this first for the full intended architecture.
- Terraform scaffolding written/edited (uncommitted as of this handoff):
  - `aws-deploy-demo/terraform/s3_cloudfront.tf` — new file, defines the S3 bucket + CloudFront distribution.
  - `aws-deploy-demo/terraform/outputs.tf` — edited, added outputs for the new resources.
  - `aws-deploy-demo/terraform/variables.tf` — edited, added variables for the new resources.
  - `aws-deploy-demo/terraform/terraform.tfvars` — present but untracked; check it's populated correctly and decide whether it belongs in version control (tfvars files often contain environment-specific values and are commonly gitignored).

## Remaining work
1. **CloudFront invalidation step** — the deploy script needs a step that invalidates the CloudFront cache after new assets are pushed to S3 (e.g. `aws cloudfront create-invalidation --distribution-id <id> --paths "/*"`), otherwise deployed changes won't show up for users until the cache expires naturally.
2. **Smoke test** — write a basic smoke test for the deployed site (e.g. curl the CloudFront URL / S3 website endpoint and assert a 200 response and expected content), to be run after deploy to confirm the site is actually live.

## Security note — action needed
During debugging in this session, `aws configure list` was run and its output (including what appeared to be an AWS access key ID and secret access key) was pasted into the chat transcript. Deliberately not reproducing those values here or in any other file.

Before continuing:
- Verify whether those were real credentials or placeholder/example values. If there is any doubt, rotate the IAM credentials for the account associated with `nicholaszhu14@gmail.com` as a precaution, since they were displayed in a chat transcript.
- Going forward, avoid pasting `aws configure list` or similar credential-revealing command output into chat/docs. Prefer `aws sts get-caller-identity` (reveals account/ARN, not secrets) when you just need to confirm which identity is active.
- Do not store AWS credentials in this repo (including `terraform.tfvars`) — use environment variables, an AWS credentials profile, or a secrets manager instead.

## Suggested next steps for a fresh agent
1. Read `aws-deploy-demo/docs/design-spec.md` for full context on the intended design.
2. Review the uncommitted Terraform changes (`git diff aws-deploy-demo/terraform/`) and confirm they match the spec.
3. Implement the CloudFront invalidation step in the deploy script.
4. Write and run the smoke test against a deployed instance.
5. Address the security note above before doing anything else with AWS credentials in this session.
