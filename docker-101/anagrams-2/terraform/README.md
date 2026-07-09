# anagrams-2 — ECS Fargate Terraform

Provisions: VPC (public subnets, no NAT), ECR repo, Secrets Manager secret
(DB password + JWT secret), RDS MySQL, IAM roles, ECS cluster/task/service,
and an ALB in front of the API.

## Prerequisites

- Terraform >= 1.5 (`brew install terraform`)
- AWS CLI configured with credentials that have permissions for VPC, ECR,
  ECS, IAM, RDS, Secrets Manager, and ELB (`aws sts get-caller-identity`
  should succeed)
- Docker, to build and push the API image

## First-time setup

```bash
cd docker-101/anagrams-2/terraform
cp terraform.tfvars.example terraform.tfvars   # edit if needed
terraform init
terraform plan     # review what will be created
terraform apply     # type "yes" to provision — this creates real, billed resources
```

## Push the API image (before or after `terraform apply`)

```bash
cd docker-101/anagrams-2/server
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin $(terraform -chdir=../terraform output -raw ecr_repository_url | cut -d/ -f1)
docker build -t anagrams-api .
docker tag anagrams-api:latest $(terraform -chdir=../terraform output -raw ecr_repository_url):latest
docker push $(terraform -chdir=../terraform output -raw ecr_repository_url):latest
```

The ECS service will show unhealthy targets until an image exists in ECR —
that's expected on the very first apply.

## Load the database schema

```bash
mysql -h $(terraform -chdir=terraform output -raw rds_endpoint) \
      -u anagrams_admin -p \
      anagrams_app < ../server/schema.sql
```
(Password: read `DB_PASSWORD` out of the secret named in the
`secrets_manager_arn` output, via the Secrets Manager console or
`aws secretsmanager get-secret-value`.)

## Verify

```bash
curl $(terraform output -raw alb_dns_name)/health
```
Expected: `{"status":"ok"}`

## Redeploy after a code change

```bash
cd docker-101/anagrams-2/server
docker build -t anagrams-api .
docker tag anagrams-api:latest <ecr_repository_url>:latest
docker push <ecr_repository_url>:latest
aws ecs update-service --cluster anagrams-cluster --service anagrams-api --force-new-deployment --region us-east-1
```

## Cost notes

- The ALB has a flat hourly charge (~$16–20/mo) even at zero traffic — the
  biggest fixed cost here.
- RDS `db.t3.micro` is free-tier eligible (750 hrs/mo) on a new AWS account;
  otherwise ~$12–15/mo.
- Fargate task (256 CPU / 512 MB) is ~$9–13/mo if left running continuously.
- No NAT Gateway is provisioned (public-subnet + security-group pattern),
  which avoids its ~$32/mo cost.

## Tear down

```bash
terraform destroy
```
Deletes everything Terraform created. Do this between practice sessions to
avoid the ALB/RDS fixed costs accumulating while nothing is being used.
