import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.milvus_client import milvus_client
from app.models.milvus_schema import get_experience_schema
import random

def test_milvus():
    print("Testing Milvus connection...")
    schema = get_experience_schema()
    milvus_client.create_collection(schema)
    
    # Test Isolation
    tenant_a = "tenant_123"
    tenant_b = "tenant_456"
    
    # Mock data
    def get_mock_data(tid, i):
        return [
            [f"id_{tid}_{i}"],
            [tid],
            [[random.random() for _ in range(768)]],
            [{"name": f"Exp {i} for {tid}", "description": "test"}],
            [f"slug-{tid}-{i}"]
        ]

    print(f"Inserting data for {tenant_a}...")
    milvus_client.insert_experience(get_mock_data(tenant_a, 1))
    
    print(f"Searching for {tenant_a}...")
    query_vector = [random.random() for _ in range(768)]
    results = milvus_client.search_experiences(tenant_a, query_vector, limit=5)
    
    found_tenant_a = False
    for hits in results:
        for hit in hits:
            print(f"Found: {hit.id}, Distance: {hit.distance}")
            if tenant_a in hit.id:
                found_tenant_a = True
    
    if found_tenant_a:
        print("SUCCESS: Found data for Tenant A")
    else:
        print("FAILED: Could not find data for Tenant A")

    print(f"Searching for {tenant_b} (should be empty if no data inserted for it)...")
    results_b = milvus_client.search_experiences(tenant_b, query_vector, limit=5)
    if len(results_b[0]) == 0:
        print("SUCCESS: Tenant B isolation confirmed (no results)")
    else:
        print(f"WARNING: Found {len(results_b[0])} results for Tenant B despite no insertion.")

if __name__ == "__main__":
    try:
        test_milvus()
    except Exception as e:
        print(f"Error during test: {e}")
        print("\nNote: Ensure Milvus is running (e.g., via Docker) at localhost:19530")
