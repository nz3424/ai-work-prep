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
