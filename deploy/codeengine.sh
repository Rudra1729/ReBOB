#!/usr/bin/env bash
# Deploy ReBOB to IBM Cloud Code Engine
set -euo pipefail

: "${CE_PROJECT:?Set CE_PROJECT to your Code Engine project name}"
: "${CE_REGION:?Set CE_REGION e.g. us-south}"
: "${CE_IMAGE:?Set CE_IMAGE e.g. us.icr.io/my-namespace/rebob:latest}"
: "${DATABASE_URL:?Set DATABASE_URL to Postgres connection string}"
: "${REBOB_ENCRYPTION_KEY:?Generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'}"
: "${REBOB_ADMIN_TOKEN:?Set a strong admin token for token issuance}"

APP_NAME="${CE_APP_NAME:-rebob}"

echo "Building and pushing image (run separately if needed):"
echo "  docker build -t \"\${CE_IMAGE}\" ."
echo "  docker push \"\${CE_IMAGE}\""

ibmcloud target -r "${CE_REGION}" >/dev/null

ibmcloud ce project select --name "${CE_PROJECT}"

ibmcloud ce app create --name "${APP_NAME}" \
  --image "${CE_IMAGE}" \
  --port 8080 \
  --cpu 0.5 --memory 1G \
  --min-scale 0 --max-scale 2 \
  --env REBOB_BACKEND=postgres \
  --env "DATABASE_URL=${DATABASE_URL}" \
  --env "REBOB_ENCRYPTION_KEY=${REBOB_ENCRYPTION_KEY}" \
  --env "REBOB_ADMIN_TOKEN=${REBOB_ADMIN_TOKEN}" \
  2>/dev/null || \
ibmcloud ce app update --name "${APP_NAME}" \
  --image "${CE_IMAGE}" \
  --env REBOB_BACKEND=postgres \
  --env "DATABASE_URL=${DATABASE_URL}" \
  --env "REBOB_ENCRYPTION_KEY=${REBOB_ENCRYPTION_KEY}" \
  --env "REBOB_ADMIN_TOKEN=${REBOB_ADMIN_TOKEN}"

echo "Deployed. URL:"
ibmcloud ce app get --name "${APP_NAME}" --output url
