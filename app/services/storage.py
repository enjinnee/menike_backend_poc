import os
from urllib.parse import quote

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

load_dotenv()


class StorageService:
    """S3-backed storage service."""

    def __init__(self):
        self.bucket_name = os.getenv("S3_BUCKET_NAME", "wakavaka-dev-resources-s3bucket")
        self.base_prefix = os.getenv("S3_BASE_PREFIX", "manike-ai/experience-images").strip("/")
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.s3_client = boto3.client("s3", region_name=self.region)

    def _build_key(self, remote_path: str) -> str:
        cleaned_path = remote_path.strip("/")
        if self.base_prefix:
            return f"{self.base_prefix}/{cleaned_path}"
        return cleaned_path

    def _public_url(self, key: str) -> str:
        encoded_key = quote(key, safe="/")
        return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{encoded_key}"

    def upload_file(self, local_path: str, remote_path: str) -> str:
        key = self._build_key(remote_path)
        try:
            self.s3_client.upload_file(local_path, self.bucket_name, key)
        except (ClientError, BotoCoreError) as exc:
            raise RuntimeError(f"S3 upload failed for {local_path}: {exc}") from exc
        return self._public_url(key)

    def upload_bytes(self, content: bytes, remote_path: str, content_type: str | None = None) -> str:
        key = self._build_key(remote_path)
        kwargs = {"Bucket": self.bucket_name, "Key": key, "Body": content}
        if content_type:
            kwargs["ContentType"] = content_type
        try:
            self.s3_client.put_object(**kwargs)
        except (ClientError, BotoCoreError) as exc:
            raise RuntimeError(f"S3 upload failed for key {key}: {exc}") from exc
        return self._public_url(key)

    def get_url(self, remote_path: str) -> str:
        key = self._build_key(remote_path)
        return self._public_url(key)


storage_service = StorageService()
