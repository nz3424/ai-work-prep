# aws-deploy-demo

**Maps to:** Itinerary Day 3 (Sun Jul 5) — see `../GOALS.md` for full context.

## Goal

Get just enough AWS to deploy something real: IAM basics, EC2 vs. ECS vs. Lambda,
S3 — then actually ship the container from `../docker-101/` to AWS.

## Tasks (mirrors Notion)

- [ ] Orient with roadmap.sh/aws (IAM, EC2 vs ECS vs Lambda, S3)
- [x] Deploy the docker-101 container to AWS (ECS Fargate) — Terraform scaffold done, `terraform apply` not yet run
- [ ] Stretch: wire up basic CI (GitHub Actions build/push on commit)

## Status

ECS Fargate chosen over Lambda (persistent MySQL connection + real-time chat
fit a long-running server better than per-invocation functions).

Terraform scaffold for the `docker-101/anagrams-2` API lives in `terraform/`:
VPC (public subnets, no NAT Gateway — security-group-based isolation
instead), ECR, Secrets Manager, RDS MySQL, IAM roles, ECS cluster/task/
service, ALB. Built via subagent-driven-development from
`docs/superpowers/plans/2026-07-09-anagrams-ecs-deploy.md`, each piece
verified with a real `terraform plan` against the live AWS account.
`terraform fmt`/`validate`/`plan` all clean (29 resources to add, 0 errors).
See `terraform/README.md` for setup/apply/verify/teardown steps.

**Not yet done:** `terraform apply` (real AWS spend, deliberately left as a
manual step — see cost notes in `terraform/README.md`), S3 + CloudFront
static deploy for the `am-client` frontend, and the CI stretch goal.

## Notes

(Log AWS gotchas, IAM policy snags, deploy configs here as you go.)
