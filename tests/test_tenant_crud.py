from fastapi.testclient import TestClient
from app.main import app
import uuid

def test_tenant_crud():
    print("Starting Tenant CRUD verification...")
    # Using 'with' triggers startup events
    with TestClient(app) as client:
        tenant_id = f"tenant-{uuid.uuid4()}"
        tenant_data = {
            "id": tenant_id,
            "name": "Test Tenant",
            "apiKey": "test-api-key",
            "config": {"theme": "dark"}
        }
        
        # 1. Create Tenant
        print(f"Testing Creation of tenant {tenant_id}...")
        try:
            response = client.post("/tenants/", json=tenant_data)
            if response.status_code != 200:
                print(f"Create failed: {response.status_code} - {response.text}")
                return

            assert response.json()["id"] == tenant_id
            print("Create successful.")
            
            # 2. Get Tenant
            print("Testing Get Tenant...")
            response = client.get(f"/tenants/{tenant_id}")
            if response.status_code != 200:
                print(f"Get Tenant failed: {response.status_code} - {response.text}")
                return
            assert response.json()["name"] == "Test Tenant"
            print("Get successful.")
            
            # 3. List Tenants
            print("Testing List Tenants...")
            response = client.get("/tenants/")
            assert response.status_code == 200
            assert any(t["id"] == tenant_id for t in response.json())
            print("List successful.")
            
            # 4. Update Tenant
            print("Testing Update Tenant...")
            tenant_data["name"] = "Updated Test Tenant"
            response = client.put(f"/tenants/{tenant_id}", json=tenant_data)
            assert response.status_code == 200
            assert response.json()["name"] == "Updated Test Tenant"
            print("Update successful.")
            
            # 5. Delete Tenant
            print("Testing Delete Tenant...")
            response = client.delete(f"/tenants/{tenant_id}")
            assert response.status_code == 200
            print("Delete successful.")
            
            # Verify deletion
            response = client.get(f"/tenants/{tenant_id}")
            assert response.status_code == 404
            print("Delete Verification successful.")
            
        except Exception as e:
            import traceback
            print(f"Test encountered an error: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    test_tenant_crud()
    print("Tenant CRUD verification script finished.")
