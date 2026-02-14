from pymilvus import FieldSchema, CollectionSchema, DataType

def get_experience_schema():
    fields = [
        # Primary Key (UUID string)
        FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
        
        # Partition Key for multi-tenancy
        FieldSchema(name="tenant_id", dtype=DataType.VARCHAR, max_length=64, is_partition_key=True),
        
        # Vector field (Gemini 768-dim)
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=768),
        
        # Metadata storage (Flexible JSON)
        FieldSchema(name="metadata", dtype=DataType.JSON),
        
        # Searchable tags / markers for fast filtering outside of vector search if needed
        FieldSchema(name="slug", dtype=DataType.VARCHAR, max_length=256),
    ]
    
    schema = CollectionSchema(fields, description="Experience vector store with multi-tenancy support")
    return schema

def get_tenant_schema():
    fields = [
        # Primary Key (UUID string)
        FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
        
        # Name
        FieldSchema(name="name", dtype=DataType.VARCHAR, max_length=256),
        
        # API Key
        FieldSchema(name="apikey", dtype=DataType.VARCHAR, max_length=128),
        
        # Flexible JSON for metadata/config
        FieldSchema(name="metadata", dtype=DataType.JSON),
        
        # Dummy vector field because Milvus requires at least one vector field for a collection to be loaded/indexed in some deployments
        # Even if we don't use it for tenants, it's safer for compatibility.
        FieldSchema(name="dummy_vector", dtype=DataType.FLOAT_VECTOR, dim=2),
    ]
    
    schema = CollectionSchema(fields, description="Tenants storage")
    return schema
