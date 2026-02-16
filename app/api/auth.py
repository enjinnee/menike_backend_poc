from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from app.core.auth import authenticate_user, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from app.core.database import get_session
from sqlmodel import Session
from datetime import timedelta

# For simplicity in POC, I'll add authentication logic here if not in core/auth.py
from app.models.sql_models import User
from app.core.auth import verify_password, ALGORITHM, SECRET_KEY

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    from sqlmodel import select
    statement = select(User).where(User.email == form_data.username)
    user = session.exec(statement).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id, "tenant_id": user.tenant_id}, 
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}
