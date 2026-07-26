import json
import os

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())  # ensure .env is loaded before boto3 reads creds

_client = None


def client():
    """Lazily build one S3 client. boto3 reads AWS_* keys from the environment."""
    global _client
    if _client is None:
        _client = boto3.client("s3", region_name=os.environ["AWS_REGION"])
    return _client


def bucket() -> str:
    name = os.environ.get("S3_BUCKET")
    if not name:
        raise RuntimeError("S3_BUCKET is not set in .env")
    return name


def object_exists(key: str) -> bool:
    try:
        client().head_object(Bucket=bucket(), Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise


def put_json(key: str, data: dict) -> None:
    client().put_object(
        Bucket=bucket(),
        Key=key,
        Body=json.dumps(data).encode("utf-8"),
        ContentType="application/json",
    )