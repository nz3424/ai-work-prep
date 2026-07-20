#!/usr/bin/env bash
set -euo pipefail
export AWS_PROFILE=headless-agents
cd "$(dirname "$0")/../terraform"

INSTANCE_ID=$(terraform output -raw instance_id)

echo "Stopping instance $INSTANCE_ID..."
aws ec2 stop-instances --instance-ids "$INSTANCE_ID" >/dev/null
aws ec2 wait instance-stopped --instance-ids "$INSTANCE_ID"

echo "Instance $INSTANCE_ID stopped."
