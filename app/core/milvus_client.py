import os
from pymilvus import connections, db, Collection, utility, DataType
from dotenv import load_dotenv

load_dotenv()

MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")
COLLECTION_NAME = "experiences"
TENANT_COLLECTION_NAME = "tenants"

class MilvusClient:
    def __init__(self):
        self.connect()

    def connect(self):
        try:
            connections.connect("default", host=MILVUS_HOST, port=MILVUS_PORT)
            print(f"Connected to Milvus at {MILVUS_HOST}:{MILVUS_PORT}")
        except Exception as e:
            print(f"Failed to connect to Milvus: {e}")

    def create_collection(self, collection_name, schema):
        if not utility.has_collection(collection_name):
            collection = Collection(name=collection_name, schema=schema)
            
            # Create HNSW index for any vector field in the schema
            for field in schema.fields:
                if field.dtype in [DataType.FLOAT_VECTOR, DataType.BINARY_VECTOR]:
                    index_params = {
                        "metric_type": "COSINE",
                        "index_type": "HNSW",
                        "params": {"M": 8, "efConstruction": 64}
                    }
                    collection.create_index(field_name=field.name, index_params=index_params)
            
            collection.load()
            print(f"Collection {collection_name} created and loaded.")
        else:
            print(f"Collection {collection_name} already exists.")

    def insert_experience(self, data):
        collection = Collection(COLLECTION_NAME)
        return collection.insert(data)

    def search_experiences(self, tenant_id, vector, limit=10):
        collection = Collection(COLLECTION_NAME)
        # Partition key (tenant_id) is automatically used for filtering when included in expr
        res = collection.search(
            data=[vector],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"ef": 64}},
            limit=limit,
            expr=f"tenant_id == '{tenant_id}'",
            output_fields=["id", "metadata"]
        )
        return res

    # Tenant CRUD Methods
    def insert_tenant(self, data):
        collection = Collection(TENANT_COLLECTION_NAME)
        return collection.insert(data)

    def get_tenant(self, tenant_id):
        collection = Collection(TENANT_COLLECTION_NAME)
        res = collection.query(
            expr=f"id == '{tenant_id}'",
            output_fields=["id", "name", "apikey", "metadata"],
            consistency_level="Strong"
        )
        return res[0] if res else None

    def list_tenants(self, limit=100):
        collection = Collection(TENANT_COLLECTION_NAME)
        res = collection.query(
            expr="",
            limit=limit,
            output_fields=["id", "name", "apikey", "metadata"],
            consistency_level="Strong"
        )
        return res

    def update_tenant(self, tenant_id, data):
        # In Milvus, update is usually an upsert if you have the primary key
        collection = Collection(TENANT_COLLECTION_NAME)
        return collection.insert(data)

    def delete_tenant(self, tenant_id):
        collection = Collection(TENANT_COLLECTION_NAME)
        return collection.delete(expr=f"id == '{tenant_id}'")

milvus_client = MilvusClient()
