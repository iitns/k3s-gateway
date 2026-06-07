#!/usr/bin/env bash
# Creates ghcr.io pull secret in the gateway namespace.
# Run this once on the k3s node (or any machine with kubectl access).
#
# Usage:
#   ./scripts/create-pull-secret.sh <github-token>
#
# The token needs at minimum 'read:packages' scope.
# On a machine with gh CLI: gh auth token

set -euo pipefail

GITHUB_USER="iitns"
GITHUB_TOKEN="${1:-}"

if [[ -z "$GITHUB_TOKEN" ]]; then
  echo "Error: GitHub token required"
  echo "Usage: $0 <github-token>"
  echo "       $0 \$(gh auth token)"
  exit 1
fi

kubectl create namespace gateway --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret docker-registry ghcr-secret \
  --namespace gateway \
  --docker-server=ghcr.io \
  --docker-username="$GITHUB_USER" \
  --docker-password="$GITHUB_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "ghcr-secret created in namespace gateway"
