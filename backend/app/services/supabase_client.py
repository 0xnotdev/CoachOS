from supabase import create_client, Client
from app.config import settings
import logging

logger = logging.getLogger(__name__)

class SupabaseService:
    def __init__(self):
        self.url = settings.SUPABASE_URL
        self.key = settings.SUPABASE_KEY
        self.client: Client | None = None
        
        if self.url and self.key:
            try:
                self.client = create_client(self.url, self.key)
                logger.info("Supabase client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {e}")
        else:
            logger.warning("Supabase URL or Key is missing. Supabase service is running in mock mode.")

    def get_client(self) -> Client:
        if not self.client:
            raise ValueError("Supabase client is not initialized.")
        return self.client

supabase_service = SupabaseService()
