#!/usr/bin/env bash
set -euo pipefail
export AWS_PROFILE=headless-agents
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

CLAUDE_DEPLOY_KEY="files/claude_deploy_key"
if [ ! -f "$CLAUDE_DEPLOY_KEY" ]; then
  echo "Missing $CLAUDE_DEPLOY_KEY — generate it first:" >&2
  echo "  ssh-keygen -t ed25519 -f terraform/$CLAUDE_DEPLOY_KEY -N \"\"" >&2
  exit 1
fi

SSH_OPTS=(-i "$KEY_PATH" -o StrictHostKeyChecking=accept-new)

# --- Deliver the write-capable deploy key out-of-band (scp, not user_data) ---
# Keeps it off the AWS-API-readable surface user_data sits on — see the note
# in templates/user_data.sh.tpl. Safe to re-run; overwrites in place.
echo "Copying claude_deploy_key to the instance..."
scp "${SSH_OPTS[@]}" "$CLAUDE_DEPLOY_KEY" "ec2-user@$PUBLIC_IP:/home/ec2-user/.ssh/claude_deploy_key"

ssh "${SSH_OPTS[@]}" "ec2-user@$PUBLIC_IP" bash -s <<'REMOTE'
set -euo pipefail
chmod 600 ~/.ssh/claude_deploy_key

# Second SSH host alias, using the write-capable key — separate from the
# `github.com` alias in ~/.ssh/config (from user_data), which stays on the
# read-only key so `git pull` keeps the training fleet's
# committed-and-pushed-only guarantee intact.
if ! grep -q "^Host github-write$" ~/.ssh/config 2>/dev/null; then
  cat >> ~/.ssh/config <<'SSH_CONFIG'

Host github-write
  HostName github.com
  IdentityFile /home/ec2-user/.ssh/claude_deploy_key
  StrictHostKeyChecking accept-new
SSH_CONFIG
fi

# Push goes over the write-capable alias; fetch/pull still uses the
# original read-only `github.com` alias.
cd ~/repo
git remote set-url --push origin git@github-write:nz3424/ai-work-prep.git

echo "Write-capable push remote configured."
REMOTE

echo
echo "Done. Remaining manual step: run 'claude setup-token' yourself (wherever"
echo "you're logged into your Claude subscription), then SSH in and add the"
echo "result to ~/.bashrc on the instance:"
echo "  echo 'export CLAUDE_CODE_OAUTH_TOKEN=<token>' >> ~/.bashrc"
