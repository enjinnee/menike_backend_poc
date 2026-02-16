from datetime import datetime
import random
import time
from typing import List, Optional
from app.models.sql_models import Scene
from sqlmodel import Session

from app.services.generators import LLMPromptEngine, ImageGenerator, VideoGenerator
from app.services.media_processor import MediaProcessor
from app.services.storage import storage_service

class SceneOrchestrator:
    def __init__(self, session: Session):
        self.session = session
        self.prompt_engine = LLMPromptEngine()
        self.image_gen = ImageGenerator()
        self.video_gen = VideoGenerator()
        self.processor = MediaProcessor()
        self.storage = storage_service

    async def create_scene(self, tenant_id: str, name: str, description: str):
        # 1. Store initial scene metadata in PostgreSQL
        scene = Scene(
            tenant_id=tenant_id,
            name=name,
            description=description,
            status="pending"
        )
        self.session.add(scene)
        self.session.commit()
        self.session.refresh(scene)
        
        # 2. Sequential Orchestration Flow
        scene.status = "processing"
        self.session.add(scene)
        self.session.commit()

        # A. Prompt Engineering (LLM)
        prompts = self.prompt_engine.generate_scene_prompts(description)
        
        # B. Generation (AI Models)
        image_path = await self.image_gen.generate(prompts["image_prompt"])
        video_path = await self.video_gen.generate(prompts["video_prompt"])
        
        # C. Media Processing (FFmpeg)
        final_video_local = self.processor.optimize_video(video_path, f"/tmp/{scene.id}_optimized.mp4")
        
        # D. Persistence (S3 upload)
        mock_media_url = self.storage.upload_file(final_video_local, f"scenes/{scene.id}.mp4")
        
        scene.media_url = mock_media_url
        scene.status = "completed"
        scene.updated_at = datetime.utcnow()
        
        self.session.add(scene)
        self.session.commit()
        print(f"Scene {scene.id} orchestration complete.")
        
        return scene

    def list_scenes(self, tenant_id: str):
        from sqlmodel import select
        statement = select(Scene).where(Scene.tenant_id == tenant_id)
        return self.session.exec(statement).all()
