#!/usr/bin/env bash
# Deploy to Cloud Run and verify the result.
#
# Flags match the requirement in server.py: the background sweep thread needs
# CPU between requests and an instance that does not scale to zero.
#
# --clear-base-image is required once a service has been deployed from
# buildpacks and then switches to a Dockerfile. Without it gcloud fails with
# "Base image is not supported for services built from Dockerfile".
#
# --memory=2Gi is not optional. sweep_pass holds a decoded frame per camera
# plus the previous pass's arrays for the diff, roughly 250 MB per set at
# ~963 cams. On Cloud Run's 512 MiB default the container is OOM-killed
# mid-pass and restarts in a loop, so scores.json never updates.

set -euo pipefail

cd "$(dirname "$0")"

SERVICE="${SERVICE:-vision}"
REGION="${REGION:-us-east1}"

gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --min-instances=1 \
  --no-cpu-throttling \
  --clear-base-image \
  --memory=2Gi \
  --cpu=2 \
  --quiet

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')

echo
echo "verifying $URL"
for path in "" "healthz" "data/cameras.json" "data/sweep/scores.json"; do
  code=$(curl -s -o /dev/null -m 30 -w '%{http_code}' "$URL/$path")
  printf '  %-28s %s\n' "/$path" "$code"
done

echo
echo "live: $URL"
