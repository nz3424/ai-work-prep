#!/usr/bin/env bash
set -euo pipefail
export AWS_PROFILE=headless-agents
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
