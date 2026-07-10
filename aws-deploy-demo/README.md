# aws-deploy-demo

**Maps to:** Itinerary Day 3 (Sun Jul 5) — see `../GOALS.md` for full context.

## Goal

Get just enough AWS to deploy something real: IAM basics, EC2 vs. ECS vs. Lambda,
S3 — then actually ship the container from `../docker-101/` to AWS.

## Tasks (mirrors Notion)

- [ ] Orient with roadmap.sh/aws (IAM, EC2 vs ECS vs Lambda, S3)
- [x] Deploy the docker-101 container to AWS (ECS Fargate) — Terraform applied, live and verified
- [x] Deploy the am-client frontend (S3 + CloudFront)
- [ ] Stretch: wire up basic CI (GitHub Actions build/push on commit)

## Status

ECS Fargate chosen over Lambda (persistent MySQL connection + real-time chat
fit a long-running server better than per-invocation functions).

Terraform in `terraform/` provisions the full stack: VPC (public subnets, no
NAT Gateway — security-group-based isolation instead), ECR, Secrets Manager,
RDS MySQL, IAM roles, ECS cluster/task/service, ALB, and an S3 bucket +
CloudFront distribution serving `am-client`. Built via
subagent-driven-development from
`docs/superpowers/plans/2026-07-09-anagrams-ecs-deploy.md` (backend) and
`docs/superpowers/plans/2026-07-09-s3-cloudfront-frontend.md` (frontend).
`terraform apply` has been run for both — all resources are live. See
`terraform/README.md` for setup/apply/verify/teardown/redeploy steps.

The API's routes are mounted under `/api` (e.g. `/api/login`, `/api/health`)
so CloudFront can route `/api/*` to the ALB and everything else to S3 from a
single HTTPS hostname, with no custom domain required.

**Not yet done:** the CI stretch goal (GitHub Actions build/push on commit).

## Notes

(Log AWS gotchas, IAM policy snags, deploy configs here as you go.)
