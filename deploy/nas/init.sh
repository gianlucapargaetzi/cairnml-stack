#!/bin/sh
# Creates the buckets and the restricted service user the mlops server uses for STS and presigning.
set -eu
mc alias set nas http://mlops-nas:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
mc mb --ignore-existing nas/artifacts nas/datasets
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
mc admin user add nas "$MLOPS_S3_ACCESS_KEY" "$MLOPS_S3_SECRET_KEY" || true
mc admin policy attach nas mlops-server --user "$MLOPS_S3_ACCESS_KEY" || true
echo "nas initialised"
