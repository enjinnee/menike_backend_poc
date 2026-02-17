import subprocess
import os
import shutil
import tempfile
import uuid
import ssl
from urllib.parse import urlparse
from urllib.request import urlopen

import boto3
import certifi

class MediaProcessor:
    """Wraps FFmpeg for media optimization and processing."""
    
    @staticmethod
    def optimize_video(input_path: str, output_path: str):
        # MOCK: FFmpeg command for optimization
        # cmd = ["ffmpeg", "-i", input_path, "-vcodec", "libx264", "-crf", "23", output_path]
        # subprocess.run(cmd, check=True)
        print(f"Optimizing video: {input_path} -> {output_path}")
        return output_path

    @staticmethod
    def stitch_scenes(video_paths: list, output_path: str):
        if not video_paths:
            print("No video paths to stitch")
            return None

        def _ensure_local(path: str) -> str:
            if path.startswith("http://") or path.startswith("https://"):
                parsed = urlparse(path)
                ext = os.path.splitext(parsed.path)[1] or ".mp4"
                local_path = os.path.join(tempfile.gettempdir(), f"clip_{uuid.uuid4().hex}{ext}")

                # Prefer boto3 for S3 URLs to avoid local SSL trust-store issues.
                host = parsed.netloc.lower()
                if ".s3." in host and host.endswith(".amazonaws.com"):
                    bucket = host.split(".s3.")[0]
                    key = parsed.path.lstrip("/")
                    boto3.client("s3").download_file(bucket, key, local_path)
                    return local_path

                ssl_ctx = ssl.create_default_context(cafile=certifi.where())
                with urlopen(path, context=ssl_ctx) as src, open(local_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                return local_path
            return path

        # 1. Create a temporary text file listing all videos
        # absolute path for safety
        list_file_path = f"/tmp/inputs_{os.getpid()}.txt" 
        local_inputs = []
        downloaded_paths = []
        
        try:
            for path in video_paths:
                local_path = _ensure_local(path)
                local_inputs.append(local_path)
                if local_path != path:
                    downloaded_paths.append(local_path)

            with open(list_file_path, "w") as f:
                for path in local_inputs:
                    # Escape single quotes in filenames for ffmpeg concat demuxer
                    safe_path = path.replace("'", "'\\''")
                    f.write(f"file '{safe_path}'\n")
            
            # 2. Run FFmpeg command to concat them
            # -f concat: use the concat demuxer
            # -safe 0: allow unsafe file paths (sometimes needed)
            # -c copy: copy streams without re-encoding (FASTEST method)
            # If formats differ, remove "-c", "copy" and let it re-encode (slower but safer)
            cmd = [
                "ffmpeg", 
                "-f", "concat", 
                "-safe", "0", 
                "-i", list_file_path, 
                "-c", "copy",
                "-y",  # Overwrite output if exists
                output_path
            ]
            
            print(f"Stitching {len(video_paths)} scenes into {output_path}...")
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"Successfully stitched video to {output_path}")
            
        except subprocess.CalledProcessError as e:
            print(f"Error stitching video: {e.stderr.decode()}")
            raise
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise
        finally:
            # Cleanup the temp list file
            if os.path.exists(list_file_path):
                os.remove(list_file_path)
            for path in downloaded_paths:
                if os.path.exists(path):
                    os.remove(path)
                
        return output_path
