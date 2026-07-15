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
# -H sets $HOME=/home/ec2-user for the sudo'd command — without it, sudoers'
# env_reset can leave $HOME=/root, so ssh looks for the deploy key in
# /root/.ssh/ instead of /home/ec2-user/.ssh/ and the clone fails auth.
sudo -u ec2-user -H git clone ${github_repo_ssh_url} /home/ec2-user/repo
