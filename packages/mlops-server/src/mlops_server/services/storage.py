"""RustFS/S3 access: presigned URLs for artifacts, STS credentials for DVC."""

from __future__ import annotations

import json
import re

import boto3
from botocore.config import Config
from mlops_common.schemas import StsResponse

_NAME_RE = re.compile(r"[A-Za-z0-9._/-]+")


def safe_artifact_name(name: str) -> str:
    if not name or len(name) > 255 or not _NAME_RE.fullmatch(name):
        raise ValueError("invalid artifact name")
    if name.startswith("/") or any(part in ("", ".", "..") for part in name.split("/")):
        raise ValueError("invalid artifact name")
    return name


def dataset_policy(bucket: str, prefix: str, write: bool) -> dict:
    object_actions = ["s3:GetObject"]
    if write:
        object_actions += ["s3:PutObject", "s3:DeleteObject"]
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
                "Resource": [f"arn:aws:s3:::{bucket}"],
                "Condition": {"StringLike": {"s3:prefix": [f"{prefix}*", prefix.rstrip("/")]}},
            },
            {
                "Effect": "Allow",
                "Action": object_actions,
                "Resource": [f"arn:aws:s3:::{bucket}/{prefix}*"],
            },
        ],
    }


class StorageService:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        artifacts_bucket: str,
        datasets_bucket: str,
        sts_ttl: int,
        s3=None,
        sts=None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._artifacts = artifacts_bucket
        self._datasets = datasets_bucket
        self._ttl = sts_ttl
        common = dict(
            endpoint_url=self._endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="us-east-1",
        )
        self._s3 = s3 or boto3.client(
            "s3", config=Config(signature_version="s3v4", s3={"addressing_style": "path"}), **common
        )
        self._sts = sts or boto3.client("sts", **common)

    def presign_put(self, key: str, expires: int = 3600) -> str:
        return self._s3.generate_presigned_url(
            "put_object", Params={"Bucket": self._artifacts, "Key": key}, ExpiresIn=expires
        )

    def presign_get(self, key: str, expires: int = 3600) -> str:
        return self._s3.generate_presigned_url(
            "get_object", Params={"Bucket": self._artifacts, "Key": key}, ExpiresIn=expires
        )

    def sts_credentials(self, project_slug: str, write: bool) -> StsResponse:
        prefix = f"{project_slug}/"
        policy = dataset_policy(self._datasets, prefix, write)
        response = self._sts.assume_role(
            RoleArn="arn:rustfs:iam:::role/mlops",
            RoleSessionName=re.sub(r"[^\w+=,.@-]", "-", project_slug)[:60] or "mlops",
            Policy=json.dumps(policy),
            DurationSeconds=self._ttl,
        )["Credentials"]
        return StsResponse(
            access_key=response["AccessKeyId"],
            secret_key=response["SecretAccessKey"],
            session_token=response["SessionToken"],
            expires_at=response["Expiration"],
            endpoint_url=self._endpoint,
            bucket=self._datasets,
            prefix=prefix,
        )


def build_storage(settings) -> StorageService | None:
    if not (settings.s3_access_key and settings.s3_secret_key):
        return None
    return StorageService(
        settings.s3_endpoint,
        settings.s3_access_key,
        settings.s3_secret_key,
        settings.artifacts_bucket,
        settings.datasets_bucket,
        settings.sts_ttl,
    )
