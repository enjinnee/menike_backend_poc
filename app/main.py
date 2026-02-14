from fastapi import FastAPI, HTTPException, Body
from typing import List, Optional
from app.models.experience import Experience
from app.models.tenant import Tenant
from app.models.milvus_schema import get_experience_schema, get_tenant_schema
from app.core.milvus_client import milvus_client, COLLECTION_NAME, TENANT_COLLECTION_NAME
import uuid
import json

app = FastAPI(title="Manike Backend API", version="1.0.0")

@app.on_event("startup")
async def startup_event():
    # Experience collection
    exp_schema = get_experience_schema()
    milvus_client.create_collection(COLLECTION_NAME, exp_schema)
    
    # Tenant collection
    tenant_schema = get_tenant_schema()
    milvus_client.create_collection(TENANT_COLLECTION_NAME, tenant_schema)

@app.get("/")
async def root():
    return {"message": "Manike Backend API is running"}

# --- Experience Endpoints ---

@app.post("/experiences/", response_model=Experience)
async def create_experience(experience: Experience):
    try:
        # Prepare data for Milvus
        metadata = experience.model_dump(exclude={"embedding"})
        
        milvus_data = [
            [experience.id],
            [experience.tenantId],
            [experience.embedding],
            [metadata],
            [experience.slug]
        ]
        
        milvus_client.insert_experience(milvus_data)
        return experience
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/experiences/search/", response_model=List[dict])
async def search_experiences(
    tenantId: str,
    embedding: List[float],
    limit: int = 10
):
    try:
        results = milvus_client.search_experiences(tenantId, embedding, limit)
        
        output = []
        for hits in results:
            for hit in hits:
                output.append({
                    "id": hit.id,
                    "distance": hit.distance,
                    "metadata": hit.entity.get("metadata")
                })
        return output
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Tenant Endpoints ---

@app.post("/tenants/", response_model=Tenant)
async def create_tenant(tenant: Tenant):
    try:
        # Prepare data for Milvus
        milvus_data = [
            [tenant.id],
            [tenant.name],
            [tenant.apiKey],
            [tenant.config],
            [[0.0, 0.0]] # Dummy vector (must be dim >= 2)
        ]
        
        milvus_client.insert_tenant(milvus_data)
        return tenant
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tenants/{tenant_id}", response_model=Tenant)
async def get_tenant(tenant_id: str):
    try:
        res = milvus_client.get_tenant(tenant_id)
        if not res:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        return Tenant(
            id=res["id"],
            name=res["name"],
            apiKey=res["apikey"],
            config=res["metadata"]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tenants/", response_model=List[Tenant])
async def list_tenants(limit: int = 100):
    try:
        results = milvus_client.list_tenants(limit)
        return [
            Tenant(
                id=res["id"],
                name=res["name"],
                apiKey=res["apikey"],
                config=res["metadata"]
            ) for res in results
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/tenants/{tenant_id}", response_model=Tenant)
async def update_tenant(tenant_id: str, tenant: Tenant):
    try:
        if tenant.id != tenant_id:
            raise HTTPException(status_code=400, detail="ID in path and body must match")
            
        milvus_data = [
            [tenant.id],
            [tenant.name],
            [tenant.apiKey],
            [tenant.config],
            [[0.0, 0.0]] # Dummy vector (must be dim >= 2)
        ]
        
        milvus_client.update_tenant(tenant_id, milvus_data)
        return tenant
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/tenants/{tenant_id}")
async def delete_tenant(tenant_id: str):
    try:
        milvus_client.delete_tenant(tenant_id)
        return {"message": f"Tenant {tenant_id} deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
