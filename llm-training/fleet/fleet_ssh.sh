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
