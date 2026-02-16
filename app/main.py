from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from app.api import auth, scenes, itinerary, experiences, tenants
from app.core.database import create_db_and_tables
from app.models.milvus_schema import get_experience_schema, get_tenant_schema
from app.core.milvus_client import milvus_client, COLLECTION_NAME, TENANT_COLLECTION_NAME

app = FastAPI(
    title="Manike B2B AI Engine", 
    version="2.0.0",
    description="Multi-tenant AI Scene Orchestrator and Itinerary Engine"
)


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
    except Exception:
        pass

app.include_router(auth.router)
app.include_router(scenes.router)
app.include_router(itinerary.router)
app.include_router(experiences.router)
app.include_router(tenants.router)

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
