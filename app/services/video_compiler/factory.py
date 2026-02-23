import os
from typing import Optional

from .base import VideoCompiler
from .local import LocalVideoCompiler


class VideoCompilerFactory:
    """Factory class to create video compiler instances based on configuration."""

    @staticmethod
    def create(provider_name: Optional[str] = None) -> VideoCompiler:
        if provider_name is None:
            provider_name = os.getenv("VIDEO_COMPILER", "local")

        provider_name = provider_name.lower()

        if provider_name == "local":
            return LocalVideoCompiler()

        elif provider_name == "cloudrun":
            from .cloudrun import CloudRunVideoCompiler
            return CloudRunVideoCompiler()

        else:
            raise ValueError(
                f"Unsupported video compiler: {provider_name}. "
                "Supported compilers: local, cloudrun"
            )
