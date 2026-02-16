from app.core.database import create_engine, engine, create_db_and_tables, get_session
from app.models.sql_models import Tenant, User
from app.core.auth import get_password_hash
from sqlmodel import Session, select

def seed_db():
    create_db_and_tables()
    
    with Session(engine) as session:
        # Create default tenant
        statement = select(Tenant).where(Tenant.id == "default-tenant")
        results = session.exec(statement)
        tenant = results.first()
        
        if not tenant:
            tenant = Tenant(
                id="default-tenant",
                name="Default B2B Partner",
                api_key="manike-test-key-123",
                config='{"theme": "dark"}'
            )
            session.add(tenant)
            print("Default tenant created.")
            
            # Create admin user
            admin_user = User(
                tenant_id="default-tenant",
                email="admin@manike.ai",
                hashed_password=get_password_hash("admin123"),
                full_name="Admin User"
            )
            session.add(admin_user)
            print("Admin user created.")
            
            session.commit()
        else:
            print("Seed data already exists.")

if __name__ == "__main__":
    seed_db()
