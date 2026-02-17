from pymilvus import FieldSchema, CollectionSchema, DataType

EMBEDDING_DIM = 128  # Must match app/services/embedding.py


def get_experience_schema():
    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
        FieldSchema(name="tenant_id", dtype=DataType.VARCHAR, max_length=64, is_partition_key=True),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=4),
        FieldSchema(name="metadata", dtype=DataType.JSON),
        FieldSchema(name="slug", dtype=DataType.VARCHAR, max_length=256),
    ]
    return CollectionSchema(fields, description="Experience vector store with multi-tenancy support")


def get_tenant_schema():
    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
        FieldSchema(name="name", dtype=DataType.VARCHAR, max_length=256),
        FieldSchema(name="apikey", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="metadata", dtype=DataType.JSON),
        FieldSchema(name="dummy_vector", dtype=DataType.FLOAT_VECTOR, dim=2),
    ]
    return CollectionSchema(fields, description="Tenants storage")


# ---------------------------------------------------------------------------
# NEW: Image Vectors - for semantic image matching
# ---------------------------------------------------------------------------
def get_image_vector_schema():
    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
        FieldSchema(name="tenant_id", dtype=DataType.VARCHAR, max_length=64, is_partition_key=True),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM),
        FieldSchema(name="metadata", dtype=DataType.JSON),  # {name, tags, location, image_url, pg_id}
    ]
    return CollectionSchema(fields, description="Image library vectors for semantic search")


# ---------------------------------------------------------------------------
# NEW: Clip Vectors - for semantic cinematic clip matching
# ---------------------------------------------------------------------------
def get_clip_vector_schema():
    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
        FieldSchema(name="tenant_id", dtype=DataType.VARCHAR, max_length=64, is_partition_key=True),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM),
        FieldSchema(name="metadata", dtype=DataType.JSON),  # {name, tags, video_url, duration, pg_id}
    ]
    return CollectionSchema(fields, description="Cinematic clip vectors for semantic search")
