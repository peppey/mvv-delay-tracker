#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="mvv-delay-tracker"
REGION="europe-west3"
SCHEDULER_SERVICE_ACCOUNT="mvv-delay-tracker-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"
RUN_API="https://run.googleapis.com/apis/run.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/jobs"

gcloud iam service-accounts create mvv-delay-tracker-scheduler \
  --project="${PROJECT_ID}" \
  --display-name="MVV Delay Tracker Cloud Scheduler" \
  2>/dev/null || true

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SCHEDULER_SERVICE_ACCOUNT}" \
  --role="roles/run.jobsExecutor" \
  --quiet

gcloud scheduler jobs create http mvv-realtime-update \
  --location="${REGION}" \
  --schedule="*/10 * * * *" \
  --time-zone="Europe/Berlin" \
  --uri="${RUN_API}/realtime-update:run" \
  --http-method=POST \
  --oauth-service-account-email="${SCHEDULER_SERVICE_ACCOUNT}" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --project="${PROJECT_ID}" \
  2>/dev/null || gcloud scheduler jobs update http mvv-realtime-update \
    --location="${REGION}" \
    --schedule="*/10 * * * *" \
    --time-zone="Europe/Berlin" \
    --uri="${RUN_API}/realtime-update:run" \
    --http-method=POST \
    --oauth-service-account-email="${SCHEDULER_SERVICE_ACCOUNT}" \
    --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
    --project="${PROJECT_ID}"

gcloud scheduler jobs create http mvv-static-update \
  --location="${REGION}" \
  --schedule="0 3 * * *" \
  --time-zone="Europe/Berlin" \
  --uri="${RUN_API}/static-update:run" \
  --http-method=POST \
  --oauth-service-account-email="${SCHEDULER_SERVICE_ACCOUNT}" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --project="${PROJECT_ID}" \
  2>/dev/null || gcloud scheduler jobs update http mvv-static-update \
    --location="${REGION}" \
    --schedule="0 3 * * *" \
    --time-zone="Europe/Berlin" \
    --uri="${RUN_API}/static-update:run" \
    --http-method=POST \
    --oauth-service-account-email="${SCHEDULER_SERVICE_ACCOUNT}" \
    --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
    --project="${PROJECT_ID}"