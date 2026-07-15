# LLM Training Track — EC2 Training Fleet Design

**Maps to:** Track 3 (`llm-training/`), infrastructure sub-project — a
simplified version of the SSH+tmux training workflow described in Dave
Blundin's "DB2 stack" writeup. See
`docs/superpowers/specs/2026-07-14-llm-training-core-design.md` for the model
code this fleet runs.

## Scope

This spec covers the training compute/orchestration layer only: an EC2
instance you can SSH into, run detached tmux sessions on (so training survives
laptop sleep/disconnect), and retrieve durable results from. It does not cover
model architecture or the tokenizer/attention/training-loop code (see the core
design spec) or the ternary/BitNet quantization work (a future spec).

**Sequencing:** this sub-project is built and verified *before*
`experiments/001-first-training-run/` executes — per the core spec, all
training runs (including the first) happen on this fleet, not locally. The
model code itself is execution-location-agnostic; this fleet is simply where
`run_fleet.sh` gets invoked.

## Architecture

**Single-tier**, deliberately simplified relative to Dave's actual two-tier
setup (cheap EC2 control box + on-demand Modal GPU rental): one EC2 instance
does the training directly. The core model is tiny (~1–5M params, trains in
minutes even on CPU), so a Modal-style GPU-rental tier is premature — it can
be added later as its own follow-up if the BitNet stretch-goal comparisons
end up needing real GPU hours.

- **Instance:** `t3.medium` (CPU-only, ~$0.04/hr) is the design default and
  `var.instance_type`'s default in `variables.tf`. The instance actually
  provisioned on this AWS account runs `t3.small` instead (~$0.0208/hr) —
  this account's Free Tier restriction blocks `t3.medium`, so
  `terraform.tfvars` overrides `instance_type` locally (gitignored, not
  committed). Swappable to a larger CPU type or a GPU instance type later via
  the same one-line Terraform variable if larger runs need it — nothing else
  in this design depends on the exact instance size.
- **Lifecycle:** stopped by default, started/stopped on demand via scripts —
  not left running continuously. A stopped (not terminated) instance retains
  its EBS volume, so setup/dependencies persist across sessions.
- **Networking:** its own dedicated VPC and Terraform state, fully separate
  from `aws-deploy-demo/`'s VPC — independent teardown, no coupling between
  this track's infra lifecycle and the anagrams app's.
- **Security group:** SSH (port 22) restricted to the current IP only (a
  Terraform variable updated per session), never `0.0.0.0/0`. SSH key pair
  generated once via Terraform/AWS, kept local, not committed to git.
- **Code delivery:** git-based — the box has the repo cloned once at setup;
  each run does `git pull` before launching. This means a run can only use
  **committed and pushed** code, which is a deliberate constraint: it forces
  every real experiment to be reproducible from git history, reinforcing the
  same discipline `experiments/*/source_archive/` already enforces locally.
- **Result durability:** an S3 bucket archives checkpoints + `training.log`
  after each run. This matches the DB2 article's explicit principle
  ("results live permanently on S3; [compute] volumes are ephemeral") applied
  to our setup: `checkpoints/` is already `.gitignore`d, so without S3 the
  only copies of a checkpoint would be the EC2 disk and whatever you
  remembered to `scp` — a real data-loss risk if the instance is ever
  terminated (e.g. when upgrading to a bigger instance type later) without
  that manual step happening first. Bucket cost is negligible at this scale
  (checkpoints are a few MB).

## Repo structure

```
llm-training/
  terraform/
    versions.tf
    network.tf          # dedicated VPC, public subnet, security group
    ec2.tf                # instance, key pair, IAM role (S3 write access)
    s3.tf                   # checkpoint/log archive bucket
    outputs.tf                # instance ID, public IP, bucket name
    README.md                  # setup, cost, teardown — mirrors
                                # aws-deploy-demo/terraform/README.md
  fleet/
    fleet_start.sh         # aws ec2 start-instances + wait-for-SSH
    fleet_stop.sh            # aws ec2 stop-instances
    fleet_ssh.sh               # ssh -i <key> ec2-user@<current-public-ip>
  (src/, experiments/, tests/, data/ — unchanged; see core design spec)
```

## Workflow

1. Commit and push any code changes locally (required — the box only ever
   pulls from GitHub).
2. `./fleet/fleet_start.sh` — starts the (already-provisioned, currently
   stopped) instance, waits until SSH is reachable.
3. `./fleet/fleet_ssh.sh` — SSH in, `tmux new -s train` (or `tmux attach` to
   resume an existing session).
4. Inside tmux: `git pull`, then run `experiments/NNN-name/run_fleet.sh`,
   which populates `source_archive/`, writes `training_config.txt`, and
   streams progress to `training.log`. Detach with `Ctrl-b d` — training
   keeps running if you close your laptop or lose the SSH connection.
5. Reattach anytime (`tmux attach -t train`) to check progress. When the run
   finishes: `run_fleet.sh`'s final step `aws s3 cp`s the checkpoint and
   `training.log` to the archive bucket (durable regardless of the
   instance's future lifecycle); optionally `scp` a local copy too for
   convenience. Write `results.md` and commit.
6. `./fleet/fleet_stop.sh` — stop the instance. This is the manual step the
   DB2 article flags as the main cost risk; since it's a stopped (not
   terminated) `t3.medium` at ~$0.04/hr, an occasional missed stop is
   low-stakes.

## Out of scope

- Modal (or any second compute tier) — deferred until/unless a run actually
  needs GPU hours beyond what a CPU instance provides.
- Automatic idle-shutdown safeguards — explicitly deferred in favor of manual
  start/stop, since the cost of a missed stop is low at this instance size.
- Multi-instance/fleet-of-many orchestration — this is a single box, not a
  fleet in the literal sense; "fleet" here just names the workflow pattern
  being borrowed from the source article.
