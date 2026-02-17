import os
from pymilvus import connections, Collection, utility, DataType
from dotenv import load_dotenv

load_dotenv()

MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")
COLLECTION_NAME = "experiences"
TENANT_COLLECTION_NAME = "tenants"
IMAGE_COLLECTION_NAME = "image_vectors"
CLIP_COLLECTION_NAME = "clip_vectors"


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
            collection = Collection(collection_name)
            for field in schema.fields:
                if field.dtype in [DataType.FLOAT_VECTOR, DataType.BINARY_VECTOR]:
                    if not collection.has_index(field_name=field.name):
                        collection.release()
                        index_params = {
                            "metric_type": "COSINE",
                            "index_type": "HNSW",
                            "params": {"M": 8, "efConstruction": 64}
                        }
                        collection.create_index(field_name=field.name, index_params=index_params)
            collection.load()
            print(f"Collection {collection_name} already exists and is now loaded (index checked).")

    # -----------------------------------------------------------------------
    # Experiences (existing)
    # -----------------------------------------------------------------------
    def insert_experience(self, data):
        collection = Collection(COLLECTION_NAME)
        return collection.insert(data)

    def search_experiences(self, tenant_id, vector, limit=10):
        collection = Collection(COLLECTION_NAME)
        res = collection.search(
            data=[vector],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"ef": 64}},
            limit=limit,
            expr=f"tenant_id == '{tenant_id}'",
            output_fields=["id", "metadata", "slug"]
        )
        return res

    def list_experiences(self, limit=100):
        collection = Collection(COLLECTION_NAME)
        return collection.query(
            expr="", limit=limit,
            output_fields=["id", "tenant_id", "metadata", "slug", "embedding"],
            consistency_level="Strong"
        )

    # -----------------------------------------------------------------------
    # Tenants (existing)
    # -----------------------------------------------------------------------
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
        return collection.query(
            expr="", limit=limit,
            output_fields=["id", "name", "apikey", "metadata"],
            consistency_level="Strong"
        )

    def update_tenant(self, tenant_id, data):
        collection = Collection(TENANT_COLLECTION_NAME)
        return collection.insert(data)

    def delete_tenant(self, tenant_id):
        collection = Collection(TENANT_COLLECTION_NAME)
        return collection.delete(expr=f"id == '{tenant_id}'")

    # -----------------------------------------------------------------------
    # Image Vectors (NEW - semantic search)
    # -----------------------------------------------------------------------
    def insert_image_vector(self, id: str, tenant_id: str, embedding: list, metadata: dict):
        """Insert an image embedding into Milvus for semantic search."""
        collection = Collection(IMAGE_COLLECTION_NAME)
        data = [[id], [tenant_id], [embedding], [metadata]]
        return collection.insert(data)

    def search_images(self, tenant_id: str, query_embedding: list, limit: int = 5):
        """Search for the most similar images using vector similarity."""
        collection = Collection(IMAGE_COLLECTION_NAME)
        results = collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"ef": 64}},
            limit=limit,
            expr=f"tenant_id == '{tenant_id}'",
            output_fields=["id", "metadata"]
        )
        return results

    def list_image_vectors(self, tenant_id: str, limit: int = 100):
        """List all image vectors for a tenant."""
        collection = Collection(IMAGE_COLLECTION_NAME)
        return collection.query(
            expr=f"tenant_id == '{tenant_id}'",
            limit=limit,
            output_fields=["id", "tenant_id", "metadata"],
            consistency_level="Strong"
        )

    # -----------------------------------------------------------------------
    # Clip Vectors (NEW - semantic search)
    # -----------------------------------------------------------------------
    def insert_clip_vector(self, id: str, tenant_id: str, embedding: list, metadata: dict):
        """Insert a cinematic clip embedding into Milvus for semantic search."""
        collection = Collection(CLIP_COLLECTION_NAME)
        data = [[id], [tenant_id], [embedding], [metadata]]
        return collection.insert(data)

    def search_clips(self, tenant_id: str, query_embedding: list, limit: int = 5):
        """Search for the most similar cinematic clips using vector similarity."""
        collection = Collection(CLIP_COLLECTION_NAME)
        results = collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"ef": 64}},
            limit=limit,
            expr=f"tenant_id == '{tenant_id}'",
            output_fields=["id", "metadata"]
        )
        return results

    def list_clip_vectors(self, tenant_id: str, limit: int = 100):
        """List all clip vectors for a tenant."""
        collection = Collection(CLIP_COLLECTION_NAME)
        return collection.query(
            expr=f"tenant_id == '{tenant_id}'",
            limit=limit,
            output_fields=["id", "tenant_id", "metadata"],
            consistency_level="Strong"
        )


milvus_client = MilvusClient()
