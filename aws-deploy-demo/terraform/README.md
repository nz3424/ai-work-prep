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
- Session Manager plugin for the AWS CLI (`brew install --cask
  session-manager-plugin`), needed for `aws ecs execute-command` — used
  below to load the DB schema

## First-time setup

```bash
cd aws-deploy-demo/terraform
cp terraform.tfvars.example terraform.tfvars   # edit if needed
terraform init
terraform plan     # review what will be created
terraform apply     # type "yes" to provision — this creates real, billed resources
```

## Push the API image (before or after `terraform apply`)

```bash
cd docker-101/anagrams-2/server
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin $(terraform -chdir=../../../aws-deploy-demo/terraform output -raw ecr_repository_url | cut -d/ -f1)
docker build -t anagrams-api .
docker tag anagrams-api:latest $(terraform -chdir=../../../aws-deploy-demo/terraform output -raw ecr_repository_url):latest
docker push $(terraform -chdir=../../../aws-deploy-demo/terraform output -raw ecr_repository_url):latest
```

The ECS service will show unhealthy targets until an image exists in ECR —
that's expected on the very first apply.

## Load the database schema

The RDS instance has `publicly_accessible = false`, and its security group
(`aws_security_group.rds` in `network.tf`) only admits port 3306 from the
ECS task's security group. That's deliberate isolation — this scaffold has
no NAT Gateway or bastion host, so nothing outside the VPC (including your
laptop) can reach the DB directly. Running `mysql -h $(terraform output -raw
rds_endpoint) ...` from your machine will just hang until it times out.

Instead, shell into the running ECS task — it's already inside the VPC and
already allowed through the RDS security group — and load the schema from
there. The service has `enable_execute_command = true` and the task role
has the `ssmmessages:*` permissions ECS Exec needs (see `iam.tf`), so this
works once a task is running (i.e. after you've pushed an image and it's
gone healthy):

```bash
cd aws-deploy-demo/terraform

# Find the running task's ID
TASK_ID=$(aws ecs list-tasks --cluster anagrams-cluster --service-name anagrams-api \
  --query 'taskArns[0]' --output text | awk -F/ '{print $NF}')

# Base64 the schema so it survives being passed as a single --command string
SCHEMA_B64=$(base64 < ../../docker-101/anagrams-2/server/schema.sql | tr -d '\n')

# One-shot: decode the schema, install a mysql client (the node:22-alpine
# image doesn't ship one — the task has outbound internet access to fetch
# it), and load it using the same DB_HOST/DB_USER/DB_PASSWORD/DB_NAME env
# vars the app itself already runs with
aws ecs execute-command \
  --cluster anagrams-cluster \
  --task "$TASK_ID" \
  --container api \
  --interactive \
  --command "/bin/sh -c 'echo $SCHEMA_B64 | base64 -d > /tmp/schema.sql && apk add --no-cache mysql-client >/dev/null 2>&1 && mysql -h \"\$DB_HOST\" -u \"\$DB_USER\" -p\"\$DB_PASSWORD\" \"\$DB_NAME\" < /tmp/schema.sql && echo SCHEMA LOADED'"
```

`SCHEMA LOADED` printing at the end means it worked. If you'd rather poke
around interactively (e.g. to check tables with `SHOW TABLES;`), drop
`--command` down to just `"/bin/sh"` and run the `apk add` / `mysql`
commands by hand once you're in.

## Verify

```bash
cd aws-deploy-demo/terraform
curl $(terraform output -raw alb_dns_name)/api/health
```
Expected: `{"status":"ok"}`

## Redeploy after a code change

```bash
cd docker-101/anagrams-2/server
docker build --platform linux/amd64 -t anagrams-api .
docker tag anagrams-api:latest <ecr_repository_url>:latest
docker push <ecr_repository_url>:latest
aws ecs update-service --cluster anagrams-cluster --service anagrams-api --force-new-deployment --region us-east-1
```

Note: `--platform linux/amd64` matters when building on Apple Silicon —
Fargate defaults to X86_64 and won't run an arm64 image.

## Deploy the client (S3 + CloudFront)

```bash
cd docker-101/anagrams-2/am-client
VITE_API_URL=/api npm run build
aws s3 sync dist/ s3://$(terraform -chdir=../../../aws-deploy-demo/terraform output -raw client_bucket_name) --delete
aws cloudfront create-invalidation \
  --distribution-id $(terraform -chdir=../../../aws-deploy-demo/terraform output -raw cloudfront_distribution_id) \
  --paths "/*"
```

The app is served from the CloudFront domain, not the ALB — run
`terraform output cloudfront_domain_name` to get the URL. The invalidation
step is required on every redeploy; without it, CloudFront keeps serving
cached (stale) assets to existing visitors.

## Cost notes

- The ALB has a flat hourly charge (~$16–20/mo) even at zero traffic — the
  biggest fixed cost here.
- RDS `db.t3.micro` is free-tier eligible (750 hrs/mo) on a new AWS account;
  otherwise ~$12–15/mo.
- Fargate task (256 CPU / 512 MB) is ~$9–13/mo if left running continuously.
- No NAT Gateway is provisioned (public-subnet + security-group pattern),
  which avoids its ~$32/mo cost.
- S3 + CloudFront (client hosting): well under $1-2/mo at demo-level
  traffic. `price_class = "PriceClass_100"` limits CloudFront to North
  America/Europe edge locations to keep cost down further.

## Tear down

```bash
cd aws-deploy-demo/terraform
terraform destroy
```
Deletes everything Terraform created. Do this between practice sessions to
avoid the ALB/RDS fixed costs accumulating while nothing is being used.
