from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class CompileResult:
    video_url: Optional[str]
    status: str  # "compiled" | "processing"
    is_async: bool


class VideoCompiler(ABC):
    @abstractmethod
    def compile(self, clip_urls: list[str], itinerary_id: str, tenant_id: str) -> CompileResult:
        """Compile a list of clip URLs into a single video.

        Returns a CompileResult indicating whether the video is ready
        (local/sync) or still processing (cloud/async).
        """
        ...
