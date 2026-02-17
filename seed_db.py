from sqlalchemy import text

from app.core.database import create_engine, engine, create_db_and_tables, get_session
from app.models.sql_models import Tenant, User
from app.core.auth import get_password_hash
from sqlmodel import Session, select

def seed_db():
    create_db_and_tables()
    
    with Session(engine) as session:
        # Lightweight migration for existing DBs: add user.role if missing.
        session.exec(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS role VARCHAR DEFAULT \'tenant_admin\''))
        session.exec(text('CREATE INDEX IF NOT EXISTS ix_user_role ON "user" (role)'))
        session.exec(text('UPDATE "user" SET role = \'tenant_admin\' WHERE role IS NULL'))
        session.commit()

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

        # Create tenant admin user
        admin_statement = select(User).where(User.email == "admin@manike.ai")
        admin_user = session.exec(admin_statement).first()
        if not admin_user:
            admin_user = User(
                tenant_id="default-tenant",
                email="admin@manike.ai",
                hashed_password=get_password_hash("admin123"),
                role="tenant_admin",
                full_name="Admin User"
            )
            session.add(admin_user)
            print("Tenant admin user created.")

        # Create super admin user for onboarding new tenants from FE
        super_statement = select(User).where(User.email == "superadmin@manike.ai")
        super_admin = session.exec(super_statement).first()
        if not super_admin:
            super_admin = User(
                tenant_id="default-tenant",
                email="superadmin@manike.ai",
                hashed_password=get_password_hash("superadmin123"),
                role="super_admin",
                full_name="Super Admin"
            )
            session.add(super_admin)
            print("Super admin user created.")

        session.commit()
        print("Seed data synced.")

if __name__ == "__main__":
    seed_db()
