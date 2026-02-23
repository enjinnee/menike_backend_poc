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
        override = run_v2.RunJobRequest.Overrides(
            container_overrides=[
                run_v2.RunJobRequest.Overrides.ContainerOverride(
                    env=[
                        run_v2.EnvVar(name="CLIP_URLS", value=json.dumps(clip_urls)),
                        run_v2.EnvVar(name="ITINERARY_ID", value=itinerary_id),
                        run_v2.EnvVar(name="TENANT_ID", value=tenant_id),
                    ],
                ),
            ],
        )

        request = run_v2.RunJobRequest(
            name=self.job_name,
            overrides=override,
        )

        # run_job is non-blocking — it returns an LRO that we intentionally
        # don't wait on. The worker updates the DB when it finishes.
        self.client.run_job(request=request)

        return CompileResult(video_url=None, status="processing", is_async=True)
