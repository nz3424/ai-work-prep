# LLM Training Track — EC2 Training Fleet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a single always-stoppable EC2 box that a training run can SSH into, run detached in `tmux`, and archive results from to S3 — the compute/orchestration layer described in `docs/superpowers/specs/2026-07-14-llm-training-fleet-design.md`.

**Architecture:** One `t3.medium` EC2 instance in its own dedicated VPC (separate Terraform state from `aws-deploy-demo/`), stopped by default, with an Elastic IP so the address never changes across stop/start — matching the source "DB2 stack" workflow's single memorized `ssh <alias>` ergonomics rather than a dynamic-lookup approach. Code reaches the box only via `git clone`/`git pull` over SSH using a read-only GitHub deploy key baked in at boot via `user_data`. An IAM instance profile scopes S3 access to one checkpoint-archive bucket. Three shell scripts (`fleet_start.sh`, `fleet_stop.sh`, `fleet_ssh.sh`) wrap the AWS CLI calls a session actually needs.

**Tech Stack:** Terraform (`hashicorp/aws` ~> 5.0, `hashicorp/tls` ~> 4.0, `hashicorp/local` ~> 2.5, `hashicorp/random` ~> 3.6), AWS (EC2, VPC, S3, IAM), bash, AWS CLI v2.

## Global Constraints

- Single EC2 instance, `t3.medium`, CPU-only (~$0.04/hr) — swappable to a GPU type later via a one-line Terraform change, not part of this plan.
- Instance is **stopped by default**; started/stopped only via `fleet_start.sh` / `fleet_stop.sh`, never left running continuously.
- **Dedicated VPC and Terraform state**, fully separate from `aws-deploy-demo/`'s VPC — independent teardown, no shared resources, no cross-references between the two `terraform/` directories.
- SSH (port 22) restricted to the current IP only via a Terraform variable with **no default** — never `0.0.0.0/0`.
- EC2 login key pair is generated once via Terraform, saved locally, and **never committed to git**.
- Instance has an **Elastic IP** so its address is stable across every stop/start — matches the source DB2-stack setup's single memorized `ssh <alias>` command, at a trivial cost (~$0.005/hr, and only while the instance is *stopped*; free while attached to a running instance).
- Code delivery is git-based: the box only ever runs `git pull`'d, committed-and-pushed code — no `rsync`/`scp` of source, no uncommitted-code shortcuts.
- An S3 bucket archives checkpoints + `training.log` after each run; bucket access from the instance is scoped to that one bucket only (least privilege).
- **Terraform state:** `*.tfstate` is gitignored and does not travel into a git worktree. Every `terraform init`/`plan`/`apply`/`destroy` in this plan must run from the **main checkout's** `llm-training/terraform/` directory (i.e. `/Users/nzhu/Documents/Claude/Projects/link-ventures-prep/llm-training/terraform`), never from a worktree copy — running `apply` from a worktree would create orphaned state disconnected from any real infrastructure history.
- `terraform apply` and `terraform destroy` create/destroy **real, billed AWS resources**. Get Nick's explicit go-ahead immediately before running either, even though this plan authorizes writing all the `.tf`/script/doc content ahead of time.

## Design decision flagged for review

This spec doesn't say how the box authenticates to pull a **private** GitHub repo (`nz3424/ai-work-prep`). This plan uses a dedicated **read-only GitHub deploy key**: generated locally with `ssh-keygen`, added to the repo's Settings → Deploy keys (read-only, no write access), private half baked into the instance via `user_data`. This is scoped tighter than a personal access token (single repo, read-only, easy to revoke) but does mean the key is readable in plaintext by anything with `ec2:DescribeInstanceAttribute` on this instance — acceptable on a single-user AWS account, called out explicitly in the README so it isn't a silent assumption. Flag if a different approach (PAT, public repo, etc.) is preferred before Task 6 executes.

## File Structure

```
llm-training/
  terraform/
    versions.tf              # Task 1 — provider requirements
    variables.tf              # Task 1 — all input variables
    terraform.tfvars.example    # Task 1 — example values to copy
    network.tf                    # Task 2 — VPC, subnet, IGW, route table, SSH security group
    s3.tf                           # Task 3 — checkpoint/log archive bucket
    iam.tf                            # Task 4 — instance role, policy, instance profile
    keypair.tf                          # Task 5 — EC2 login key pair (generated, saved locally)
    templates/
      user_data.sh.tpl                   # Task 6 — boot script: packages + deploy key + git clone
    ec2.tf                                 # Task 7 — the instance + Elastic IP
    outputs.tf                              # Task 8 — instance id/IP, bucket name, key path
    README.md                                 # Task 10 — setup, cost, teardown, SSH alias
    files/                                      # gitignored — deploy key + generated login key land here
  fleet/
    fleet_start.sh            # Task 9 — start instance, wait for SSH
    fleet_stop.sh               # Task 9 — stop instance
    fleet_ssh.sh                  # Task 9 — SSH in using the current public IP
.gitignore                       # Task 1 — add llm-training/terraform/files/
```

---

### Task 1: Terraform scaffolding — provider, variables, example tfvars

**Files:**
- Create: `llm-training/terraform/versions.tf`
- Create: `llm-training/terraform/variables.tf`
- Create: `llm-training/terraform/terraform.tfvars.example`
- Modify: `.gitignore` (repo root)

**Interfaces:**
- Consumes: nothing (first task)
- Produces: `var.aws_region`, `var.project_name`, `var.vpc_cidr`, `var.public_subnet_cidr`, `var.availability_zone`, `var.my_ip_cidr`, `var.instance_type`, `var.github_repo_ssh_url`, `var.github_deploy_key_path` — every later task's `.tf` file references these by name, so names/types here are load-bearing.

- [ ] **Step 1: Create `versions.tf`**

```hcl
terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = var.project_name
      ManagedBy = "terraform"
    }
  }
}
```

- [ ] **Step 2: Create `variables.tf`**

```hcl
variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short name used to prefix/tag all resources"
  type        = string
  default     = "llm-training-fleet"
}

variable "vpc_cidr" {
  description = "CIDR block for the dedicated fleet VPC"
  type        = string
  default     = "10.1.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for the single public subnet (one instance, one AZ)"
  type        = string
  default     = "10.1.1.0/24"
}

variable "availability_zone" {
  description = "AZ the instance and its subnet live in"
  type        = string
  default     = "us-east-1a"
}

variable "my_ip_cidr" {
  description = "Your current public IP in CIDR form (e.g. 1.2.3.4/32) — SSH ingress is restricted to this. No default on purpose: set it fresh every session via -var or terraform.tfvars, never leave stale."
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type for the training box"
  type        = string
  default     = "t3.medium"
}

variable "github_repo_ssh_url" {
  description = "SSH clone URL for the repo the fleet pulls from"
  type        = string
  default     = "git@github.com:nz3424/ai-work-prep.git"
}

variable "github_deploy_key_path" {
  description = "Local path (relative to this terraform/ dir) to the private half of the read-only GitHub deploy key — generated manually per README, never committed"
  type        = string
  default     = "files/github_deploy_key"
}
```

- [ ] **Step 3: Create `terraform.tfvars.example`**

```hcl
aws_region   = "us-east-1"
project_name = "llm-training-fleet"
my_ip_cidr   = "1.2.3.4/32" # run: curl -s https://checkip.amazonaws.com — update every session
```

- [ ] **Step 4: Add the fleet's local-secrets directory to `.gitignore`**

Open `.gitignore` at the repo root and add this line under the existing `# --- Terraform / IaC, if you end up using it for AWS ---` section (the `*.tfstate`/`.terraform/` lines already there):

```
llm-training/terraform/files/
```

- [ ] **Step 5: Validate**

```bash
cd llm-training/terraform
terraform init
terraform validate
```

Expected: `Success! The configuration is valid.` (An empty root module — just a provider block and variables, no resources yet — is valid.)

- [ ] **Step 6: Commit**

```bash
git add llm-training/terraform/versions.tf llm-training/terraform/variables.tf \
  llm-training/terraform/terraform.tfvars.example .gitignore
git commit -m "llm-training: add Terraform scaffolding for the training fleet"
```

---

### Task 2: Network — dedicated VPC, public subnet, SSH security group

**Files:**
- Create: `llm-training/terraform/network.tf`

**Interfaces:**
- Consumes: `var.project_name`, `var.vpc_cidr`, `var.public_subnet_cidr`, `var.availability_zone`, `var.my_ip_cidr` (Task 1)
- Produces: `aws_vpc.fleet.id`, `aws_subnet.fleet.id`, `aws_security_group.fleet_ssh.id` — Task 7 (EC2 instance) references all three.

- [ ] **Step 1: Create `network.tf`**

```hcl
resource "aws_vpc" "fleet" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.project_name}-vpc"
  }
}

resource "aws_internet_gateway" "fleet" {
  vpc_id = aws_vpc.fleet.id

  tags = {
    Name = "${var.project_name}-igw"
  }
}

resource "aws_subnet" "fleet" {
  vpc_id                  = aws_vpc.fleet.id
  cidr_block               = var.public_subnet_cidr
  availability_zone         = var.availability_zone
  map_public_ip_on_launch    = true

  tags = {
    Name = "${var.project_name}-public"
  }
}

resource "aws_route_table" "fleet" {
  vpc_id = aws_vpc.fleet.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.fleet.id
  }

  tags = {
    Name = "${var.project_name}-public-rt"
  }
}

resource "aws_route_table_association" "fleet" {
  subnet_id      = aws_subnet.fleet.id
  route_table_id = aws_route_table.fleet.id
}

resource "aws_security_group" "fleet_ssh" {
  name        = "${var.project_name}-ssh-sg"
  description = "SSH from the current session's IP only — never 0.0.0.0/0"
  vpc_id      = aws_vpc.fleet.id

  ingress {
    description = "SSH from current IP"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.my_ip_cidr]
  }

  egress {
    description = "All outbound (git pull, S3 upload, package installs)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-ssh-sg"
  }
}
```

- [ ] **Step 2: Validate and plan**

```bash
cd llm-training/terraform
terraform validate
terraform plan -var="my_ip_cidr=1.2.3.4/32"
```

Expected: `Success!` from validate; plan shows 6 resources to add (VPC, IGW, subnet, route table, route table association, security group), no errors.

- [ ] **Step 3: Commit**

```bash
git add llm-training/terraform/network.tf
git commit -m "llm-training: add dedicated VPC, subnet, and SSH security group"
```

---

### Task 3: S3 checkpoint/log archive bucket

**Files:**
- Create: `llm-training/terraform/s3.tf`

**Interfaces:**
- Consumes: `var.project_name` (Task 1)
- Produces: `aws_s3_bucket.checkpoints.id`, `aws_s3_bucket.checkpoints.arn` — Task 4 (IAM policy) and Task 8 (outputs) reference these.

- [ ] **Step 1: Create `s3.tf`**

```hcl
resource "random_id" "checkpoint_bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "checkpoints" {
  bucket = "${var.project_name}-checkpoints-${random_id.checkpoint_bucket_suffix.hex}"

  tags = {
    Name = "${var.project_name}-checkpoints"
  }
}

resource "aws_s3_bucket_public_access_block" "checkpoints" {
  bucket = aws_s3_bucket.checkpoints.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```

- [ ] **Step 2: Validate and plan**

```bash
cd llm-training/terraform
terraform validate
terraform plan -var="my_ip_cidr=1.2.3.4/32"
```

Expected: `Success!`; plan now also shows the bucket + public access block + random_id (3 new resources on top of Task 2's 6).

- [ ] **Step 3: Commit**

```bash
git add llm-training/terraform/s3.tf
git commit -m "llm-training: add S3 checkpoint/log archive bucket"
```

---

### Task 4: IAM role, scoped S3 policy, instance profile

**Files:**
- Create: `llm-training/terraform/iam.tf`

**Interfaces:**
- Consumes: `var.project_name` (Task 1), `aws_s3_bucket.checkpoints.arn` (Task 3)
- Produces: `aws_iam_instance_profile.fleet.name` — Task 7 (EC2 instance) references this.

- [ ] **Step 1: Create `iam.tf`**

```hcl
data "aws_iam_policy_document" "fleet_ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "fleet" {
  name               = "${var.project_name}-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.fleet_ec2_assume_role.json
}

# Scoped to exactly the checkpoint bucket — the instance can read/write its
# own archive and nothing else in the account.
data "aws_iam_policy_document" "fleet_s3_checkpoints" {
  statement {
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.checkpoints.arn,
      "${aws_s3_bucket.checkpoints.arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "fleet_s3_checkpoints" {
  name   = "${var.project_name}-s3-checkpoints"
  role   = aws_iam_role.fleet.id
  policy = data.aws_iam_policy_document.fleet_s3_checkpoints.json
}

resource "aws_iam_instance_profile" "fleet" {
  name = "${var.project_name}-instance-profile"
  role = aws_iam_role.fleet.name
}
```

- [ ] **Step 2: Validate and plan**

```bash
cd llm-training/terraform
terraform validate
terraform plan -var="my_ip_cidr=1.2.3.4/32"
```

Expected: `Success!`; plan adds the IAM role, role policy, and instance profile (3 more resources).

- [ ] **Step 3: Commit**

```bash
git add llm-training/terraform/iam.tf
git commit -m "llm-training: add IAM role scoped to the checkpoint bucket"
```

---

### Task 5: EC2 login key pair (generated, saved locally)

**Files:**
- Create: `llm-training/terraform/keypair.tf`

**Interfaces:**
- Consumes: `var.project_name` (Task 1)
- Produces: `aws_key_pair.fleet.key_name` — Task 7 (EC2 instance) references this. `local_sensitive_file.fleet_private_key.filename` — Task 8 (outputs) and `fleet_ssh.sh` (Task 9) reference this path.

- [ ] **Step 1: Create `keypair.tf`**

```hcl
resource "tls_private_key" "fleet" {
  algorithm = "ED25519"
}

resource "aws_key_pair" "fleet" {
  key_name   = "${var.project_name}-login-key"
  public_key = tls_private_key.fleet.public_key_openssh

  tags = {
    Name = "${var.project_name}-login-key"
  }
}

# Private half never touches git — files/ is gitignored (Task 1) and this
# resource writes with 0600 permissions, matching what ssh requires anyway.
resource "local_sensitive_file" "fleet_private_key" {
  content         = tls_private_key.fleet.private_key_openssh
  filename        = "${path.module}/files/fleet_login_key.pem"
  file_permission = "0600"
}
```

- [ ] **Step 2: Validate and plan**

```bash
cd llm-training/terraform
terraform validate
terraform plan -var="my_ip_cidr=1.2.3.4/32"
```

Expected: `Success!`; plan adds the tls_private_key, aws_key_pair, and local_sensitive_file (3 more resources). No file is written yet — that happens on `apply` (Task 11).

- [ ] **Step 3: Commit**

```bash
git add llm-training/terraform/keypair.tf
git commit -m "llm-training: add Terraform-generated EC2 login key pair"
```

---

### Task 6: Boot script — packages, GitHub deploy key, repo clone

**Files:**
- Create: `llm-training/terraform/templates/user_data.sh.tpl`

**Interfaces:**
- Consumes: `var.github_repo_ssh_url`, `var.github_deploy_key_path` (Task 1) — read via `templatefile()` in Task 7's `ec2.tf`, not directly by this file. This task's template expects two template variables at render time: `github_deploy_key` (string, private key contents) and `github_repo_ssh_url` (string).
- Produces: a fully rendered boot script consumed by `aws_instance.fleet.user_data` in Task 7.

- [ ] **Step 1: Create `templates/user_data.sh.tpl`**

```bash
#!/bin/bash
set -euxo pipefail

# --- Base packages: git + tmux (survive laptop sleep/disconnect) + python3 ---
# python deps for the model itself (torch, etc.) are installed by
# run_fleet.sh at run time, not here — this box is infra-only, per the
# fleet design spec's scope boundary against the core model spec.
dnf install -y git tmux python3.11 python3.11-pip

# --- Read-only GitHub deploy key, so `git pull` works without a human ---
mkdir -p /home/ec2-user/.ssh
cat > /home/ec2-user/.ssh/github_deploy_key <<'DEPLOY_KEY'
${github_deploy_key}
DEPLOY_KEY
chmod 600 /home/ec2-user/.ssh/github_deploy_key
chown ec2-user:ec2-user /home/ec2-user/.ssh/github_deploy_key

cat > /home/ec2-user/.ssh/config <<'SSH_CONFIG'
Host github.com
  IdentityFile /home/ec2-user/.ssh/github_deploy_key
  StrictHostKeyChecking accept-new
SSH_CONFIG
chmod 600 /home/ec2-user/.ssh/config
chown ec2-user:ec2-user /home/ec2-user/.ssh/config

# --- Clone once at boot; every run does `git pull` from here on ---
sudo -u ec2-user git clone ${github_repo_ssh_url} /home/ec2-user/repo
```

- [ ] **Step 2: Validate**

```bash
cd llm-training/terraform
terraform validate
```

Expected: `Success!` — `templatefile()` isn't called until Task 7, so `terraform validate` doesn't need the actual deploy key file to exist yet.

- [ ] **Step 3: Commit**

```bash
git add llm-training/terraform/templates/user_data.sh.tpl
git commit -m "llm-training: add fleet boot script (packages, deploy key, git clone)"
```

---

### Task 7: EC2 instance

**Files:**
- Create: `llm-training/terraform/ec2.tf`

**Interfaces:**
- Consumes: `var.project_name`, `var.instance_type`, `var.github_repo_ssh_url`, `var.github_deploy_key_path` (Task 1); `aws_subnet.fleet.id`, `aws_security_group.fleet_ssh.id` (Task 2); `aws_iam_instance_profile.fleet.name` (Task 4); `aws_key_pair.fleet.key_name` (Task 5); `templates/user_data.sh.tpl` (Task 6)
- Produces: `aws_instance.fleet.id`, `aws_eip.fleet.public_ip` — Task 8 (outputs) and the fleet scripts (Task 9, via `terraform output`) depend on these. Note `aws_eip.fleet.public_ip` (not `aws_instance.fleet.public_ip`) is the address that stays stable across stop/start.

- [ ] **Step 1: Create `ec2.tf`**

```hcl
# Latest Amazon Linux 2023 AMI, resolved at plan time via SSM — avoids
# hardcoding a region-specific AMI ID that goes stale.
data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_instance" "fleet" {
  ami                    = data.aws_ssm_parameter.al2023_ami.value
  instance_type           = var.instance_type
  subnet_id                 = aws_subnet.fleet.id
  vpc_security_group_ids      = [aws_security_group.fleet_ssh.id]
  iam_instance_profile           = aws_iam_instance_profile.fleet.name
  key_name                          = aws_key_pair.fleet.key_name
  associate_public_ip_address          = true

  # Explicit rather than trusting the AL2023 AMI's default (~8GB) — enough
  # headroom for Python packages (torch, etc., installed later by
  # run_fleet.sh) plus checkpoints/logs, without over-provisioning like the
  # DB2 stack's 2TB (sized for datasets far larger than tinyshakespeare-scale
  # data). Resizable later in-place (bump this value + `terraform apply`,
  # then `growpart`/`xfs_growfs` on the box) if it's ever not enough.
  root_block_device {
    volume_size = 20
    volume_type = "gp3"
  }

  user_data = templatefile("${path.module}/templates/user_data.sh.tpl", {
    github_deploy_key   = file("${path.module}/${var.github_deploy_key_path}")
    github_repo_ssh_url = var.github_repo_ssh_url
  })

  tags = {
    Name = "${var.project_name}-instance"
  }
}

# Elastic IP so the address is stable across every stop/start — matches
# the source DB2-stack workflow's single memorized `ssh <alias>` command
# instead of a dynamic-lookup approach. EIP-to-instance association
# persists automatically across stop/start (standard EC2-VPC behavior),
# no re-association needed in fleet_start.sh.
resource "aws_eip" "fleet" {
  instance = aws_instance.fleet.id
  domain   = "vpc"

  tags = {
    Name = "${var.project_name}-eip"
  }
}
```

- [ ] **Step 2: Validate**

```bash
cd llm-training/terraform
terraform validate
```

Expected: `Success!` — validate only checks syntax/references, not that `files/github_deploy_key` exists on disk yet.

- [ ] **Step 3: Commit**

```bash
git add llm-training/terraform/ec2.tf
git commit -m "llm-training: add the EC2 training instance with a stable Elastic IP"
```

---

### Task 8: Outputs

**Files:**
- Create: `llm-training/terraform/outputs.tf`

**Interfaces:**
- Consumes: `aws_instance.fleet.id`, `aws_eip.fleet.public_ip` (Task 7); `aws_s3_bucket.checkpoints.id` (Task 3); `local_sensitive_file.fleet_private_key.filename` (Task 5)
- Produces: `terraform output -raw instance_id`, `terraform output -raw instance_public_ip`, `terraform output -raw checkpoint_bucket_name`, `terraform output -raw ssh_private_key_path` — Task 9's fleet scripts and Task 10's README SSH-alias instructions call these by exact name.

- [ ] **Step 1: Create `outputs.tf`**

```hcl
output "instance_id" {
  description = "EC2 instance ID — used by fleet_start.sh / fleet_stop.sh"
  value       = aws_instance.fleet.id
}

output "instance_public_ip" {
  description = "Elastic IP — stable across every stop/start, so it's safe to hardcode into ~/.ssh/config or trust as a cached value, unlike a default EC2 public IP."
  value       = aws_eip.fleet.public_ip
}

output "checkpoint_bucket_name" {
  description = "S3 bucket that archives checkpoints + training.log"
  value       = aws_s3_bucket.checkpoints.id
}

output "ssh_private_key_path" {
  description = "Local path to the EC2 login private key — used by fleet_ssh.sh"
  value       = local_sensitive_file.fleet_private_key.filename
}
```

- [ ] **Step 2: Validate**

```bash
cd llm-training/terraform
terraform validate
terraform fmt -check
```

Expected: `Success!` from validate. `fmt -check` should print nothing (no diffs) — if it lists files, run `terraform fmt` and re-check before committing.

- [ ] **Step 3: Commit**

```bash
git add llm-training/terraform/outputs.tf
git commit -m "llm-training: add Terraform outputs for instance id/IP, bucket, and key path"
```

---

### Task 9: Fleet scripts — start, stop, ssh

**Files:**
- Create: `llm-training/fleet/fleet_start.sh`
- Create: `llm-training/fleet/fleet_stop.sh`
- Create: `llm-training/fleet/fleet_ssh.sh`

**Interfaces:**
- Consumes: `terraform output -raw instance_id`, `terraform output -raw instance_public_ip`, `terraform output -raw ssh_private_key_path` (Task 8) — run against the **main checkout's** `llm-training/terraform/` state, per the Global Constraints note.
- Produces: three executable entry points a training session runs directly (`./fleet/fleet_start.sh` etc.), as described in the design spec's Workflow section.

- [ ] **Step 1: Create `fleet_start.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../terraform"

INSTANCE_ID=$(terraform output -raw instance_id)
PUBLIC_IP=$(terraform output -raw instance_public_ip)

echo "Starting instance $INSTANCE_ID..."
aws ec2 start-instances --instance-ids "$INSTANCE_ID" >/dev/null
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

# The Elastic IP (Task 7) stays the same across every stop/start, so the
# terraform output is trustworthy here — no live describe-instances query
# needed just to find the current address.
echo "Waiting for SSH on $PUBLIC_IP:22..."
until nc -z -w2 "$PUBLIC_IP" 22 2>/dev/null; do
  sleep 5
done

echo "Instance $INSTANCE_ID is running at $PUBLIC_IP — SSH is reachable. Run ./fleet_ssh.sh to connect."
```

- [ ] **Step 2: Create `fleet_stop.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../terraform"

INSTANCE_ID=$(terraform output -raw instance_id)

echo "Stopping instance $INSTANCE_ID..."
aws ec2 stop-instances --instance-ids "$INSTANCE_ID" >/dev/null
aws ec2 wait instance-stopped --instance-ids "$INSTANCE_ID"

echo "Instance $INSTANCE_ID stopped."
```

- [ ] **Step 3: Create `fleet_ssh.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../terraform"

INSTANCE_ID=$(terraform output -raw instance_id)
KEY_PATH=$(terraform output -raw ssh_private_key_path)
PUBLIC_IP=$(terraform output -raw instance_public_ip)

STATE=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].State.Name' --output text)
if [ "$STATE" != "running" ]; then
  echo "Instance $INSTANCE_ID is '$STATE', not running — run ./fleet_start.sh first." >&2
  exit 1
fi

exec ssh -i "$KEY_PATH" -o StrictHostKeyChecking=accept-new "ec2-user@$PUBLIC_IP"
```

- [ ] **Step 4: Make all three executable and syntax-check them**

```bash
cd llm-training/fleet
chmod +x fleet_start.sh fleet_stop.sh fleet_ssh.sh
bash -n fleet_start.sh && bash -n fleet_stop.sh && bash -n fleet_ssh.sh
```

Expected: no output from any `bash -n` call (silent = valid syntax). If `shellcheck` is installed, also run `shellcheck fleet_start.sh fleet_stop.sh fleet_ssh.sh` and resolve any warnings before continuing.

- [ ] **Step 5: Commit**

```bash
git add llm-training/fleet/fleet_start.sh llm-training/fleet/fleet_stop.sh llm-training/fleet/fleet_ssh.sh
git commit -m "llm-training: add fleet_start/fleet_stop/fleet_ssh scripts"
```

---

### Task 10: `terraform/README.md`

**Files:**
- Create: `llm-training/terraform/README.md`

**Interfaces:**
- Consumes: every variable/output name defined in Tasks 1–8 (documents them for a human operator).
- Produces: the setup/cost/teardown doc a future session (or Task 11) follows verbatim.

- [ ] **Step 1: Create `README.md`**

```markdown
# llm-training-fleet — EC2 Training Fleet Terraform

Provisions: a dedicated VPC (single public subnet, no NAT), an SSH-only
security group scoped to your current IP, an S3 bucket for checkpoint/log
archival, an IAM role+instance profile scoped to that bucket, and a
`t3.medium` EC2 instance that clones this repo at boot via a read-only
GitHub deploy key.

Separate from `aws-deploy-demo/terraform/` — its own VPC, its own state,
independent teardown.

## Prerequisites

- Terraform >= 1.5 (`brew install terraform`)
- AWS CLI v2 configured with credentials that can manage VPC, EC2, S3, and
  IAM (`aws sts get-caller-identity` should succeed)
- An SSH key pair for a **read-only GitHub deploy key** (separate from the
  EC2 login key, which Terraform generates for you)

## First-time setup

### 1. Generate the GitHub deploy key

```bash
cd llm-training/terraform
mkdir -p files
ssh-keygen -t ed25519 -f files/github_deploy_key -N "" -C "llm-training-fleet deploy key"
```

Add the **public** half (`files/github_deploy_key.pub`) to the repo:
GitHub → `nz3424/ai-work-prep` → Settings → Deploy keys → Add deploy key →
paste the contents, leave "Allow write access" **unchecked** (read-only).

The private half stays local — `llm-training/terraform/files/` is
gitignored. Note: this key is embedded in the instance's `user_data`,
which is readable in plaintext by anything with
`ec2:DescribeInstanceAttribute` on this instance. Acceptable for a
single-user AWS account; don't reuse this pattern in a shared-account
setting without rethinking it.

### 2. Set your current IP

```bash
curl -s https://checkip.amazonaws.com
```

Copy `terraform.tfvars.example` to `terraform.tfvars` and set `my_ip_cidr`
to that IP with `/32`, e.g. `my_ip_cidr = "1.2.3.4/32"`. **Update this
every session** — your IP changes, and a stale value just means SSH stops
working until you fix it (fails safe, never opens to `0.0.0.0/0`).

```bash
cp terraform.tfvars.example terraform.tfvars   # then edit my_ip_cidr
```

### 3. Provision

```bash
terraform init
terraform plan     # review what will be created
terraform apply     # type "yes" — creates real, billed resources
```

The instance starts **running** immediately after `apply` (AWS default);
run `../fleet/fleet_stop.sh` once you've confirmed it booted cleanly, so
it doesn't sit running between sessions.

### 4. (Optional) Add an SSH alias

The instance has an Elastic IP, so it's safe to hardcode — matching Dave
Blundin's DB2-stack setup, where the box is reachable with a single `ssh
<alias>` from his Mac. Add to `~/.ssh/config`:

```
Host llm-fleet
  HostName <terraform output -raw instance_public_ip>
  User ec2-user
  IdentityFile <repo-root>/llm-training/terraform/files/fleet_login_key.pem
```

Then `ssh llm-fleet` works directly — useful for tools that expect a
plain SSH host (VS Code Remote-SSH, `scp`, `rsync`) without going through
`fleet_ssh.sh`. The wrapper script remains the primary entry point since
it also checks the instance is actually running first.

## Everyday workflow

See the design spec's Workflow section
(`docs/superpowers/specs/2026-07-14-llm-training-fleet-design.md`) for the
full per-session flow. Quick reference:

```bash
cd llm-training/fleet
./fleet_start.sh    # start the instance, wait for SSH
./fleet_ssh.sh        # SSH in
# ... tmux new -s train, git pull, run experiments/NNN/run_fleet.sh ...
./fleet_stop.sh          # stop when done
```

## Cost notes

- `t3.medium`, stopped by default: ~$0.04/hr only while running.
- A **stopped** (not terminated) instance keeps its EBS volume — setup and
  cloned repo persist across sessions. The 20GB gp3 root volume costs
  ~$1.60/mo regardless of instance state (much smaller than the DB2
  stack's 2TB, since this project's data/checkpoints are tinyshakespeare-scale,
  not the larger datasets that setup was sized for). Resizable in-place
  later if it's ever not enough — see the comment in `ec2.tf`.
- Elastic IP: free while attached to a running instance; ~$0.005/hr
  (~$3.60/mo if never started) while the instance is stopped. The
  tradeoff for a stable, hardcode-able address — see "Add an SSH alias"
  above.
- S3 checkpoint bucket: negligible, checkpoints are a few MB.
- No NAT Gateway, no ALB — this is a bare public-subnet instance, avoiding
  the ~$32/mo NAT cost `aws-deploy-demo/` accepts for its ECS setup.

## Tear down

```bash
cd llm-training/terraform
terraform destroy
```

Deletes everything Terraform created, including the S3 bucket — if you
want to keep the checkpoint archive, empty and remove that resource from
state first, or `aws s3 sync` its contents elsewhere before destroying.
```

- [ ] **Step 2: Commit**

```bash
git add llm-training/terraform/README.md
git commit -m "llm-training: add fleet Terraform README"
```

---

### Task 11: Provision, verify end-to-end, and stop

This task runs real Terraform against real AWS and costs real money —
**get Nick's explicit go-ahead immediately before Step 2 (`terraform
apply`) and Step 7 (`terraform destroy`, if run).** Everything up to here
in this plan only writes files; this is the first task with a live-infra
side effect.

**Files:** none created — this task exercises Tasks 1–10 together.

**Interfaces:**
- Consumes: all outputs from Tasks 1–10.
- Produces: a running, verified fleet instance — the deliverable the whole plan exists to produce.

- [ ] **Step 1: Confirm you're operating on the main checkout's state**

```bash
cd /Users/nzhu/Documents/Claude/Projects/link-ventures-prep/llm-training/terraform
pwd   # must NOT contain .claude/worktrees
git rev-parse --show-toplevel
```

If this plan was executed inside a worktree, the `.tf` files were written
there — copy or merge them into the main checkout's `llm-training/`
before running `apply`, since `.tfstate` never travels into a worktree
and applying from the worktree would create disconnected state.

- [ ] **Step 2: Apply (after explicit confirmation)**

Precondition: the GitHub deploy key must already exist at `files/github_deploy_key`
(generate it per the README's "First-time setup" Step 1 if you haven't) —
`terraform plan` reads this file directly and fails immediately if it's missing.

```bash
terraform init
terraform plan
terraform apply
```

Expected: apply succeeds, instance transitions to `running`.

- [ ] **Step 3: Verify SSH and the boot script**

```bash
../fleet/fleet_ssh.sh
```

Once connected:
```bash
git -C repo status          # confirms the deploy key + clone worked
tmux -V                       # confirms tmux installed
python3.11 --version            # confirms python installed
```

Expected: `repo` is a clean checkout of `nz3424/ai-work-prep` on its
default branch; `tmux`/`python3.11` both report versions with no errors.

- [ ] **Step 4: Verify S3 write access from the instance**

The IAM policy (Task 4) deliberately scopes S3 access to exactly the
checkpoint bucket's ARN — it does not grant `s3:ListAllMyBuckets`, so
`aws s3 ls` with no bucket argument won't work from inside the instance.
Get the bucket name from Terraform first, from your **local** shell
(not the SSH session):

```bash
# Run from llm-training/terraform, before connecting via SSH:
BUCKET=$(terraform output -raw checkpoint_bucket_name)
echo "Bucket: $BUCKET"   # note this value for the SSH session below
```

Then connect via SSH and use that bucket name directly:
```bash
echo "fleet smoke test" > /tmp/smoke.txt
aws s3 cp /tmp/smoke.txt "s3://<BUCKET-FROM-ABOVE>/smoke.txt"
aws s3 ls "s3://<BUCKET-FROM-ABOVE>/"
rm /tmp/smoke.txt
```

Expected: the `cp` succeeds and `smoke.txt` shows up in the `ls` output —
confirms the IAM instance profile grants exactly the S3 access it needs
(and no more — `aws s3 ls` with no bucket argument would fail here, which
is correct behavior, not a bug).
Exit the SSH session (`exit`) once confirmed.

- [ ] **Step 5: Verify the stop/start cycle and IP stability**

```bash
cd llm-training/fleet
IP_BEFORE=$(terraform -chdir=../terraform output -raw instance_public_ip)
./fleet_stop.sh
aws ec2 describe-instances --instance-ids "$(terraform -chdir=../terraform output -raw instance_id)" \
  --query 'Reservations[0].Instances[0].State.Name' --output text
```

Expected: prints `stopped`.

```bash
./fleet_start.sh
IP_AFTER=$(terraform -chdir=../terraform output -raw instance_public_ip)
[ "$IP_BEFORE" = "$IP_AFTER" ] && echo "IP stable: $IP_AFTER" || echo "MISMATCH: $IP_BEFORE vs $IP_AFTER"
```

Expected: `fleet_start.sh` blocks until SSH is reachable, then exits
cleanly; the IP comparison prints `IP stable: ...` — confirms the
instance survives a stop/start cycle (repo + installed packages persist
on the retained EBS volume) and that the Elastic IP (Task 7) really does
stay fixed, so the cached Terraform output stays trustworthy without a
live re-query.

- [ ] **Step 5b: Verify the SSH alias (if set up per the README)**

```bash
ssh llm-fleet "echo alias works"
```

Expected: prints `alias works` — confirms the `~/.ssh/config` entry from
Task 10 connects correctly using the stable IP.

- [ ] **Step 6: Leave it stopped**

```bash
./fleet_stop.sh
```

This is the end state Task 11 should leave the fleet in — stopped, not
running, per the Global Constraints.

- [ ] **Step 7 (optional, only if Nick wants to tear down instead of keeping the fleet provisioned):**

```bash
cd ../terraform
terraform destroy
```

Only run this after explicit confirmation — it deletes the checkpoint S3
bucket and everything else Terraform created.
