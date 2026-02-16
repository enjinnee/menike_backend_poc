from fastapi import APIRouter, Depends, HTTPException
from typing import List
from app.models.tenant import Tenant
from app.core.milvus_client import milvus_client

router = APIRouter(prefix="/tenants", tags=["Tenant Management"])

@router.post("/", response_model=Tenant)
async def create_tenant(tenant: Tenant):
    try:
        milvus_data = [
            [tenant.id],
            [tenant.name],
            [tenant.apiKey],
            [tenant.config],
            [[0.0, 0.0]]
        ]
        milvus_client.insert_tenant(milvus_data)
        return tenant
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{tenant_id}", response_model=Tenant)
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

@router.get("/", response_model=List[Tenant])
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

@router.put("/{tenant_id}", response_model=Tenant)
async def update_tenant(tenant_id: str, tenant: Tenant):
    try:
        if tenant.id != tenant_id:
            raise HTTPException(status_code=400, detail="ID in path and body must match")
        milvus_data = [
            [tenant.id],
            [tenant.name],
            [tenant.apiKey],
            [tenant.config],
            [[0.0, 0.0]]
        ]
        milvus_client.update_tenant(tenant_id, milvus_data)
        return tenant
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{tenant_id}")
async def delete_tenant(tenant_id: str):
    try:
        milvus_client.delete_tenant(tenant_id)
        return {"message": f"Tenant {tenant_id} deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
