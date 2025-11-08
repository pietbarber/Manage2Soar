#!/usr/bin/env bash

# Script to update the Kubernetes secret with DJANGO_DEBUG=False
# Run this once to set up production environment variables

echo "Updating Kubernetes secret to set DJANGO_DEBUG=False for production..."

# Get the current secret and add DJANGO_DEBUG=False
kubectl patch secret manage2soar-env --type='merge' -p='{"data":{"DJANGO_DEBUG":"RmFsc2U="}}'

# Note: "RmFsc2U=" is base64 encoding of "False"
# You can verify with: echo "RmFsc2U=" | base64 -d

echo "✅ Updated manage2soar-env secret with DJANGO_DEBUG=False"
echo "ℹ️  Next deployment will use DEBUG=False in production"
