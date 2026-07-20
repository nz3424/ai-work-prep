#!/bin/bash
set -euxo pipefail

# --- Base packages: git + tmux (survive laptop sleep/disconnect) + python3 ---
# python deps for the model itself (torch, etc.) are installed by
# run_fleet.sh at run time, not here — this box is infra-only, per the
# fleet design spec's scope boundary against the core model spec.
dnf install -y git tmux python3.11 python3.11-pip

# --- Node.js + Claude Code CLI, for interactive/long-running Claude Code
# sessions inside the same tmux-survives-disconnect workflow as training
# runs. Auth (CLAUDE_CODE_OAUTH_TOKEN) and the write-capable git deploy key
# are delivered out-of-band via fleet_claude_setup.sh after boot, not here —
# user_data is readable in plaintext by anything with
# ec2:DescribeInstanceAttribute on this instance, so secrets more sensitive
# than the read-only clone key stay off this path.
#
# npm install runs as ec2-user with a user-owned prefix, not as root — a
# root-owned global npm prefix leaves `claude` unable to self-update later
# (it always runs as ec2-user), which is exactly what happened the first
# time this ran as a plain root-context `npm install -g`.
dnf install -y nodejs npm
sudo -u ec2-user -H bash -c '
  mkdir -p ~/.npm-global
  npm config set prefix ~/.npm-global
  echo "export PATH=~/.npm-global/bin:\$PATH" >> ~/.bashrc
  export PATH=~/.npm-global/bin:$PATH
  npm install -g @anthropic-ai/claude-code
'

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
