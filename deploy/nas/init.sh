#!/bin/sh
# Creates the buckets and the restricted service user the mlops server uses for STS and presigning.
# Any failure stops the script, except the "already exists" case, which is the normal re-run path.
set -eu
mc alias set nas http://mlops-nas:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
mc mb --ignore-existing nas/artifacts nas/datasets || { echo "bucket creation failed" >&2; exit 1; }
cat > /tmp/mlops-server-policy.json <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": ["s3:*"],
      "Resource": ["arn:aws:s3:::artifacts", "arn:aws:s3:::artifacts/*",
                   "arn:aws:s3:::datasets", "arn:aws:s3:::datasets/*"] }
  ]
}
JSON
mc admin policy info nas mlops-server >/dev/null 2>&1 || mc admin policy create nas mlops-server /tmp/mlops-server-policy.json

# run_or_exists OUTPUT-PREFIX COMMAND...: runs COMMAND; a failure is tolerated only if mc says it already exists.
run_or_exists() {
  if out=$("$@" 2>&1); then
    return 0
  fi
  case "$out" in
    *"already exist"*|*"already attached"*|*"already been attached"*) return 0 ;;
  esac
  echo "failed: $*" >&2
  echo "$out" >&2
  exit 1
}

run_or_exists mc admin user add nas "$MLOPS_S3_ACCESS_KEY" "$MLOPS_S3_SECRET_KEY"
run_or_exists mc admin policy attach nas mlops-server --user "$MLOPS_S3_ACCESS_KEY"
echo "nas initialised"
