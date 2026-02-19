import os
import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/heygen", tags=["HeyGen"])


class HeyGenTokenRequest(BaseModel):
    session_id: str


@router.post("/token")
async def get_heygen_token(req: HeyGenTokenRequest):
    """Generate a HeyGen LiveAvatar session token."""
    from app.chat.session import chat_session_store

    if not req.session_id or not chat_session_store.exists(req.session_id):
        raise HTTPException(status_code=400, detail="Invalid session")

    heygen_api_key = os.environ.get("HEYGEN_API_KEY")
    if not heygen_api_key or heygen_api_key == "your_heygen_api_key_here":
        raise HTTPException(status_code=500, detail="HeyGen API key not configured")

    avatar_id = os.environ.get("HEYGEN_AVATAR_ID", "")
    voice_id = os.environ.get("HEYGEN_VOICE_ID", "")

    request_body = {
        "mode": "FULL",
        "avatar_id": avatar_id if avatar_id else None,
        "avatar_persona": {},
    }
    if voice_id:
        request_body["avatar_persona"]["voice_id"] = voice_id

    print(f"[DEBUG] LiveAvatar API request:")
    print(f"  URL: https://api.liveavatar.com/v1/sessions/token")
    print(f"  API Key (first 10 chars): {heygen_api_key[:10]}...")
    print(f"  Body: {request_body}")

    try:
        response = requests.post(
            "https://api.liveavatar.com/v1/sessions/token",
            headers={
                "X-API-KEY": heygen_api_key,
                "accept": "application/json",
                "content-type": "application/json",
            },
            json=request_body,
        )

        print(f"[DEBUG] LiveAvatar API response:")
        print(f"  Status: {response.status_code}")
        print(f"  Body: {response.text[:500]}")

        if response.status_code == 200:
            token_data = response.json()
            return {
                "token": token_data.get("data", {}).get("session_token"),
                "avatar_id": avatar_id,
                "voice_id": voice_id,
            }
        else:
            error_msg = f"LiveAvatar API error: {response.status_code}"
            try:
                error_data = response.json()
                error_msg = f"LiveAvatar API error: {error_data.get('message', error_data)}"
            except Exception:
                error_msg = f"LiveAvatar API error: {response.status_code} - {response.text}"
            print(f"[ERROR] {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Exception in get_heygen_token: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_heygen_config():
    """Get HeyGen configuration for the frontend."""
    heygen_api_key = os.environ.get("HEYGEN_API_KEY")
    return {
        "avatar_id": os.environ.get("HEYGEN_AVATAR_ID", "default"),
        "voice_id": os.environ.get("HEYGEN_VOICE_ID", "default"),
        "configured": bool(heygen_api_key) and heygen_api_key != "your_heygen_api_key_here",
    }
