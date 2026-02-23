import os
import subprocess

from .base import VideoCompiler, CompileResult
from app.services.media_processor import MediaProcessor
from app.services.storage import storage_service


class LocalVideoCompiler(VideoCompiler):
    """Compiles video locally using FFmpeg (synchronous)."""

    def __init__(self):
        self.media_processor = MediaProcessor()

    def compile(self, clip_urls: list[str], itinerary_id: str, tenant_id: str) -> CompileResult:
        output_path = f"/tmp/final_video_{itinerary_id}.mp4"

        try:
            final_local = self.media_processor.stitch_scenes(clip_urls, output_path)
        except subprocess.CalledProcessError:
            raise RuntimeError(
                "Unable to compile final video due to incompatible clip encoding/timestamps."
            )

        gcs_key = f"tenants/{tenant_id}/final-video/{itinerary_id}.mp4"
        video_url = storage_service.upload_file(final_local, gcs_key)

        # Clean up temp file
        if os.path.exists(output_path):
            os.remove(output_path)

        return CompileResult(video_url=video_url, status="compiled", is_async=False)
