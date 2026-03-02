"""
Map Clip Generator
==================
Renders an animated MP4 showing a route between two GPS coordinates overlaid
on a real map tile basemap (OpenStreetMap via contextily).

Output: portrait-orientation (720×1280) MP4 compatible with the existing
        FFmpeg normalize/concat pipeline in MediaProcessor.stitch_scenes().

Usage:
    from app.services.map_clip_generator import map_clip_generator

    result = map_clip_generator.generate_and_upload(
        from_lat=7.180, from_lon=79.885,
        to_lat=7.957, to_lon=80.760,
        from_label="BIA Airport",
        to_label="Sigiriya",
        itinerary_id="abc123",
        tenant_id="tenant_xyz",
        transition_idx=0,
        transport_type="car",
        duration_seconds=2.5,
    )
    print(result.gcs_url)   # GCS URL of the generated clip
"""

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Optional

import numpy as np

# CRITICAL: use non-interactive backend before importing pyplot (server has no display)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import imageio

from app.services.storage import storage_service

logger = logging.getLogger(__name__)


@dataclass
class MapClipResult:
    gcs_url: str
    duration: float     # actual clip duration in seconds


class MapClipGenerator:
    """
    Generates animated map transition clips.

    Each clip shows:
    - A real OSM/CartoDB basemap (fetched via contextily)
    - A grey static route line from origin to destination
    - A moving dot tracing the route frame-by-frame
    - A growing coloured progress line behind the dot
    - Origin (green) and destination (red) marker dots
    - Location labels

    Falls back to a plain coloured background if tile fetching fails.
    """

    DEFAULT_FPS = 24
    DEFAULT_DURATION = 2.5      # seconds
    FRAME_WIDTH = 720
    FRAME_HEIGHT = 1280
    PADDING_FACTOR = 0.35       # bounding-box padding as fraction of route span

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def generate(
        self,
        from_lat: float,
        from_lon: float,
        to_lat: float,
        to_lon: float,
        from_label: str,
        to_label: str,
        transport_type: str = "car",
        duration_seconds: float = DEFAULT_DURATION,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Render the route animation and write it to *output_path* as an MP4.

        Returns the output_path.
        """
        if output_path is None:
            output_path = f"/tmp/map_{uuid.uuid4().hex}.mp4"

        fps = self.DEFAULT_FPS
        n_frames = max(int(duration_seconds * fps), 1)

        # Compute bounding box with padding
        lat_span = abs(to_lat - from_lat)
        lon_span = abs(to_lon - from_lon)
        pad = max(self.PADDING_FACTOR * max(lat_span, lon_span), 0.3)

        min_lat = min(from_lat, to_lat) - pad
        max_lat = max(from_lat, to_lat) + pad
        min_lon = min(from_lon, to_lon) - pad
        max_lon = max(from_lon, to_lon) + pad

        # Interpolate route points
        route_lats, route_lons = self._interpolate_route(
            from_lat, from_lon, to_lat, to_lon, n_frames, transport_type
        )

        # Build figure (portrait 9:16 at 80 dpi → 720×1280 px)
        dpi = 80
        fig_w = self.FRAME_WIDTH / dpi
        fig_h = self.FRAME_HEIGHT / dpi
        fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
        fig.patch.set_facecolor("#1a1a2e")
        ax.set_facecolor("#1a1a2e")
        ax.set_xlim(min_lon, max_lon)
        ax.set_ylim(min_lat, max_lat)
        ax.set_aspect("auto")
        ax.axis("off")
        plt.tight_layout(pad=0)

        # Attempt to add real map tiles
        self._add_basemap(ax, min_lon, max_lon, min_lat, max_lat)

        # Static route line (faint grey)
        ax.plot(
            [from_lon, to_lon], [from_lat, to_lat],
            color="#888888", linewidth=1.5, alpha=0.4, zorder=3, linestyle="--"
        )

        # Origin / destination dots
        ax.scatter([from_lon], [from_lat], color="#4CAF50", s=120, zorder=6,
                   edgecolors="white", linewidths=1.5)
        ax.scatter([to_lon], [to_lat], color="#F44336", s=120, zorder=6,
                   edgecolors="white", linewidths=1.5)

        # Labels
        label_offset_lat = (max_lat - min_lat) * 0.025
        ax.text(from_lon, from_lat + label_offset_lat, from_label,
                color="white", fontsize=7, ha="center", va="bottom",
                fontweight="bold", zorder=7,
                bbox=dict(boxstyle="round,pad=0.2", fc="#1a1a2e", alpha=0.6, ec="none"))
        ax.text(to_lon, to_lat + label_offset_lat, to_label,
                color="white", fontsize=7, ha="center", va="bottom",
                fontweight="bold", zorder=7,
                bbox=dict(boxstyle="round,pad=0.2", fc="#1a1a2e", alpha=0.6, ec="none"))

        # Transport type text label at centre of route (ASCII-safe, no emoji)
        icon = self._transport_label(transport_type)
        mid_lat = (from_lat + to_lat) / 2
        mid_lon = (from_lon + to_lon) / 2
        ax.text(mid_lon, mid_lat, icon, color="#FF9800", fontsize=7,
                ha="center", va="center", zorder=7, alpha=0.9,
                fontstyle="italic",
                bbox=dict(boxstyle="round,pad=0.15", fc="#1a1a2e", alpha=0.5, ec="none"))

        # Animated elements (updated per frame)
        progress_line, = ax.plot([], [], color="#FF9800", linewidth=2.5, zorder=4)
        moving_dot, = ax.plot([], [], "o", color="#FF9800", markersize=8,
                               markeredgecolor="white", markeredgewidth=1.5, zorder=5)

        fig.canvas.draw()

        # Render frames
        frames = []
        for i in range(n_frames):
            # Easing: use ease-in-out for smoother motion
            t = self._ease_in_out(i / max(n_frames - 1, 1))
            seg_end = max(1, int(t * n_frames))

            progress_line.set_data(route_lons[:seg_end], route_lats[:seg_end])
            moving_dot.set_data([route_lons[min(i, len(route_lons) - 1)]],
                                 [route_lats[min(i, len(route_lats) - 1)]])

            fig.canvas.draw()
            # buffer_rgba is the modern API; tostring_rgb was removed in matplotlib 3.8+
            buf = np.frombuffer(fig.canvas.buffer_rgba(), dtype=np.uint8)
            frame_rgba = buf.reshape(self.FRAME_HEIGHT, self.FRAME_WIDTH, 4)
            frame = frame_rgba[:, :, :3]   # drop alpha → RGB
            frames.append(frame.copy())

        plt.close(fig)

        # Write MP4 via imageio-ffmpeg
        imageio.mimwrite(
            output_path,
            frames,
            fps=fps,
            quality=7,
            macro_block_size=None,
        )

        logger.info("Map clip written: %s (%d frames, %.1fs)", output_path, n_frames, duration_seconds)
        return output_path

    def generate_and_upload(
        self,
        from_lat: float,
        from_lon: float,
        to_lat: float,
        to_lon: float,
        from_label: str,
        to_label: str,
        itinerary_id: str,
        tenant_id: str,
        transition_idx: int,
        transport_type: str = "car",
        duration_seconds: float = DEFAULT_DURATION,
    ) -> MapClipResult:
        """
        Render the map animation, upload to GCS, and return the result.

        GCS key: tenants/{tenant_id}/map-transitions/{itinerary_id}_{transition_idx}.mp4
        """
        local_path = f"/tmp/map_{itinerary_id}_{transition_idx}_{uuid.uuid4().hex[:6]}.mp4"
        try:
            self.generate(
                from_lat, from_lon, to_lat, to_lon,
                from_label, to_label,
                transport_type, duration_seconds, local_path,
            )
            gcs_key = f"tenants/{tenant_id}/map-transitions/{itinerary_id}_{transition_idx}.mp4"
            gcs_url = storage_service.upload_file(local_path, gcs_key)
            logger.info("Map clip uploaded: %s", gcs_url)
            return MapClipResult(gcs_url=gcs_url, duration=duration_seconds)
        finally:
            if os.path.exists(local_path):
                os.remove(local_path)

    @staticmethod
    def make_cache_key(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> str:
        """Deterministic cache key for the MapTransition table."""
        return f"{from_lat:.4f}_{from_lon:.4f}_{to_lat:.4f}_{to_lon:.4f}"

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    def _interpolate_route(
        self,
        from_lat: float, from_lon: float,
        to_lat: float, to_lon: float,
        n_frames: int,
        transport_type: str,
    ):
        """Return (lats, lons) arrays of length n_frames."""
        if transport_type == "flight":
            # Great-circle arc using pyproj
            try:
                from pyproj import Geod
                geod = Geod(ellps="WGS84")
                lonlats = geod.npts(from_lon, from_lat, to_lon, to_lat, n_frames - 2)
                lons = [from_lon] + [p[0] for p in lonlats] + [to_lon]
                lats = [from_lat] + [p[1] for p in lonlats] + [to_lat]
                # Resample to exactly n_frames
                indices = np.linspace(0, len(lats) - 1, n_frames).astype(int)
                return np.array(lats)[indices], np.array(lons)[indices]
            except ImportError:
                logger.warning("pyproj not installed — using linear interpolation for flight")

        lats = np.linspace(from_lat, to_lat, n_frames)
        lons = np.linspace(from_lon, to_lon, n_frames)
        return lats, lons

    def _add_basemap(self, ax, min_lon, max_lon, min_lat, max_lat):
        """Attempt to add a CartoDB Positron basemap; silently skip on failure."""
        try:
            import contextily
            ax.set_xlim(min_lon, max_lon)
            ax.set_ylim(min_lat, max_lat)
            contextily.add_basemap(
                ax,
                crs="EPSG:4326",
                source=contextily.providers.CartoDB.Positron,
                zoom="auto",
                alpha=0.85,
                zorder=1,
            )
        except Exception as exc:
            logger.warning("Could not fetch map tiles (%s) — using plain background", exc)

    @staticmethod
    def _ease_in_out(t: float) -> float:
        """Smooth ease-in-out curve: t in [0, 1] → eased value in [0, 1]."""
        return t * t * (3.0 - 2.0 * t)

    @staticmethod
    def _transport_label(transport_type: str) -> str:
        """Return a short ASCII label for the transport type (no emoji — font-safe)."""
        labels = {
            "flight": "by air",
            "train": "by train",
            "ferry": "by ferry",
            "bus": "by bus",
            "car": "by car",
            "tuk-tuk": "by tuk-tuk",
        }
        return labels.get(transport_type, "by road")


# Module-level singleton
map_clip_generator = MapClipGenerator()
