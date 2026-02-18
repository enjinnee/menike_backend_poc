from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.api import auth, scenes, itinerary, experiences, tenants, images, cinematic_clips, admin
from app.api import chat as chat_api
from app.api import pages as pages_api
from app.core.database import create_db_and_tables
from app.models.milvus_schema import (
    get_experience_schema, get_tenant_schema, 
    get_image_vector_schema, get_clip_vector_schema
)
from app.core.milvus_client import (
    milvus_client, COLLECTION_NAME, TENANT_COLLECTION_NAME,
    IMAGE_COLLECTION_NAME, CLIP_COLLECTION_NAME
)

app = FastAPI(
    title="Manike B2B AI Engine",
    version="2.0.0",
    description="Multi-tenant AI Scene Orchestrator and Itinerary Engine"
)

# Serve static files (CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
async def startup_event():
    # 1. Initialize PostgreSQL (SQLModel)
    try:
        create_db_and_tables()
    except Exception:
        pass # Handle in database logs
    
    # 2. Initialize Milvus
    try:
        exp_schema = get_experience_schema()
        milvus_client.create_collection(COLLECTION_NAME, exp_schema)
        
        tenant_schema = get_tenant_schema()
        milvus_client.create_collection(TENANT_COLLECTION_NAME, tenant_schema)
        
        img_schema = get_image_vector_schema()
        milvus_client.create_collection(IMAGE_COLLECTION_NAME, img_schema)
        
        clip_schema = get_clip_vector_schema()
        milvus_client.create_collection(CLIP_COLLECTION_NAME, clip_schema)
    except Exception:
        pass

app.include_router(pages_api.router)
app.include_router(auth.router)
app.include_router(chat_api.router)
app.include_router(scenes.router)
app.include_router(itinerary.router)
app.include_router(images.router)
app.include_router(cinematic_clips.router)
app.include_router(experiences.router)
app.include_router(tenants.router)
app.include_router(admin.router)


@app.get("/docs-api", include_in_schema=False)
async def api_docs():
    return RedirectResponse(url="/docs")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
