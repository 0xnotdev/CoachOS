from fastapi import Header, HTTPException, Depends
from app.config import settings
from app.services.supabase_client import supabase_service
import jwt
import logging
import asyncio

logger = logging.getLogger(__name__)

async def get_current_user_id(
    authorization: str = Header(None, description="Bearer Supabase Auth Token")
) -> str:
    """
    Validates and decodes the Supabase JWT to extract the subject (auth_user_id).
    """
    if not authorization:
        logger.warning("Unauthenticated request blocked. Missing Authorization header.")
        raise HTTPException(
            status_code=401, 
            detail="Authentication credentials required. Please provide a Bearer JWT."
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, 
            detail="Invalid token format. Must start with 'Bearer '"
        )

    token = authorization.split(" ")[1]
    
    jwt_secret = settings.SUPABASE_JWT_SECRET
    if not jwt_secret:
        logger.critical("SUPABASE_JWT_SECRET is not configured in settings. Auth verification blocked.")
        raise HTTPException(
            status_code=500, 
            detail="Authentication service configuration error."
        )

    try:
        decoded_payload = jwt.decode(
            token, 
            jwt_secret, 
            algorithms=["HS256"], 
            options={"verify_aud": False, "verify_signature": True}
        )
        user_id = decoded_payload.get("sub")
        
        if not user_id:
            raise HTTPException(
                status_code=401, 
                detail="Subject claim missing from token claims"
            )
            
        return user_id

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Authentication token has expired")
    except jwt.InvalidTokenError as e:
        logger.error(f"JWT Decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid auth token signature")
    except Exception as e:
        logger.error(f"Authentication processing error: {e}")
        raise HTTPException(status_code=500, detail="Authentication server error")

async def get_current_coach_id(
    user_id: str = Depends(get_current_user_id)
) -> str:
    """
    Resolves the decoded subject (auth_user_id) to the database coaches.id.
    """
    db = supabase_service.get_client()
    try:
        coach_res = await asyncio.to_thread(
            lambda: db.table("coaches")
            .select("id")
            .eq("auth_user_id", user_id)
            .execute()
        )
        
        if not coach_res.data:
            logger.error(f"No Coach entity links to authenticated user ID {user_id}")
            raise HTTPException(
                status_code=403, 
                detail="Your user profile is not registered as a coach. Please register your account configuration."
            )
            
        return coach_res.data[0]["id"]
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to resolve coach_id for auth user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error resolving coach profile.")
