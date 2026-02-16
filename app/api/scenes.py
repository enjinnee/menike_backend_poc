from fastapi import APIRouter, Depends, HTTPException
from app.services.orchestrator import SceneOrchestrator
from app.core.auth import get_current_tenant_id
from app.core.database import get_session
from sqlmodel import Session
from pydantic import BaseModel

router = APIRouter(prefix="/scenes", tags=["Scene Orchestrator"])

class SceneCreate(BaseModel):
    name: str
    description: str

@router.post("/")
async def create_scene(
    scene_data: SceneCreate,
    tenant_id: str = Depends(get_current_tenant_id),
    session: Session = Depends(get_session)
):
    orchestrator = SceneOrchestrator(session)
    scene = await orchestrator.create_scene(tenant_id, scene_data.name, scene_data.description)
    return scene

@router.get("/")
async def list_scenes(
    tenant_id: str = Depends(get_current_tenant_id),
    session: Session = Depends(get_session)
):
    orchestrator = SceneOrchestrator(session)
    return orchestrator.list_scenes(tenant_id)
