import json
import os

from google.cloud import run_v2

from .base import VideoCompiler, CompileResult


class CloudRunVideoCompiler(VideoCompiler):
    """Offloads video compilation to a Cloud Run Job (asynchronous)."""

    def __init__(self):
        self.job_name = os.environ["CLOUD_RUN_JOB_NAME"]
        self.region = os.getenv("CLOUD_RUN_REGION", "us-central1")
        self.client = run_v2.JobsClient()

    def compile(self, clip_urls: list[str], itinerary_id: str, tenant_id: str) -> CompileResult:
        """Legacy mode: stitch a fixed list of clip URLs."""
        env_overrides = [
            run_v2.EnvVar(name="CLIP_URLS",      value=json.dumps(clip_urls)),
            run_v2.EnvVar(name="ITINERARY_ID",   value=itinerary_id),
            run_v2.EnvVar(name="TENANT_ID",      value=tenant_id),
            run_v2.EnvVar(name="CINEMATIC",      value="false"),
        ]
        return self._run_job(env_overrides)

    def compile_cinematic(
        self,
        itinerary_id: str,
        tenant_id: str,
        target_seconds: float = 45.0,
    ) -> CompileResult:
        """Cinematic mode: full pipeline (map transitions + Pexels + pacing)."""
        env_overrides = [
            run_v2.EnvVar(name="ITINERARY_ID",   value=itinerary_id),
            run_v2.EnvVar(name="TENANT_ID",      value=tenant_id),
            run_v2.EnvVar(name="CINEMATIC",      value="true"),
            run_v2.EnvVar(name="TARGET_SECONDS", value=str(target_seconds)),
        ]
        return self._run_job(env_overrides)

    # ------------------------------------------------------------------
    def _run_job(self, env_overrides: list) -> CompileResult:
        override = run_v2.RunJobRequest.Overrides(
            container_overrides=[
                run_v2.RunJobRequest.Overrides.ContainerOverride(
                    env=env_overrides,
                ),
            ],
        )
        request = run_v2.RunJobRequest(
            name=self.job_name,
            overrides=override,
        )
        # Non-blocking — the worker updates the DB when it finishes.
        self.client.run_job(request=request)
        return CompileResult(video_url=None, status="processing", is_async=True)
