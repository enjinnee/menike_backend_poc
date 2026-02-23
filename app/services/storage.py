import os
from datetime import timedelta

import google.auth
import google.auth.transport.requests
from google.cloud import storage
from dotenv import load_dotenv

load_dotenv()


class StorageService:
    """GCS-backed storage service."""

    def __init__(self):
        self.bucket_name = os.getenv("GCS_BUCKET_NAME", "manike-ai-media")
        self.base_prefix = os.getenv("GCS_BASE_PREFIX", "experience-images").strip("/")
        self.signed_url_expiry_minutes = int(os.getenv("GCS_SIGNED_URL_EXPIRY_MINUTES", "60"))
        self.credentials, _ = google.auth.default()
        self.client = storage.Client(credentials=self.credentials)
        self.bucket = self.client.bucket(self.bucket_name)

    def _build_key(self, remote_path: str) -> str:
        cleaned_path = remote_path.strip("/")
        if self.base_prefix:
            return f"{self.base_prefix}/{cleaned_path}"
        return cleaned_path

    def _signed_url(self, key: str) -> str:
        # Refresh credentials so the token is valid for signing
        auth_req = google.auth.transport.requests.Request()
        self.credentials.refresh(auth_req)
        blob = self.bucket.blob(key)
        return blob.generate_signed_url(
            expiration=timedelta(minutes=self.signed_url_expiry_minutes),
            method="GET",
            version="v4",
            credentials=self.credentials,
        )

    def upload_file(self, local_path: str, remote_path: str) -> str:
        key = self._build_key(remote_path)
        blob = self.bucket.blob(key)
        try:
            blob.upload_from_filename(local_path)
        except Exception as exc:
            raise RuntimeError(f"GCS upload failed for {local_path}: {exc}") from exc
        return self._signed_url(key)

    def upload_bytes(self, content: bytes, remote_path: str, content_type: str | None = None) -> str:
        key = self._build_key(remote_path)
        blob = self.bucket.blob(key)
        try:
            blob.upload_from_string(content, content_type=content_type)
        except Exception as exc:
            raise RuntimeError(f"GCS upload failed for key {key}: {exc}") from exc
        return self._signed_url(key)

    def get_url(self, remote_path: str) -> str:
        key = self._build_key(remote_path)
        return self._signed_url(key)


storage_service = StorageService()
