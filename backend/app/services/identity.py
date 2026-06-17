import asyncio
from uuid import UUID
from app.services.supabase_client import supabase_service
import logging

logger = logging.getLogger(__name__)

class IdentityResolutionService:
    def __init__(self):
        # We check client availability locally
        self.db = None

    def _get_db(self):
        if not self.db:
            self.db = supabase_service.get_client()
        return self.db

    async def resolve_identity(self, source: str, external_id: str) -> UUID | None:
        """
        Resolves a source-specific ID (e.g., Stripe cus_123) to a global Person UUID.
        Runs in a threadpool to prevent blocking the async event loop.
        """
        try:
            return await asyncio.to_thread(self._resolve_identity_sync, source, external_id)
        except Exception as e:
            logger.error(f"Error resolving identity for {source}:{external_id} -> {e}")
            return None

    def _resolve_identity_sync(self, source: str, external_id: str) -> UUID | None:
        db = self._get_db()
        response = db.table('identities') \
            .select('person_id') \
            .eq('source', source) \
            .eq('external_id', external_id) \
            .execute()
        
        if response.data and len(response.data) > 0:
            return UUID(response.data[0]['person_id'])
        return None

    async def link_identity(self, person_id: UUID, source: str, external_id: str) -> bool:
        """
        Links a new external ID to an existing person.
        """
        try:
            await asyncio.to_thread(self._link_identity_sync, person_id, source, external_id)
            return True
        except Exception as e:
            logger.error(f"Error linking identity: {e}")
            return False

    def _link_identity_sync(self, person_id: UUID, source: str, external_id: str):
        db = self._get_db()
        db.table('identities').insert({
            "person_id": str(person_id),
            "source": source,
            "external_id": external_id
        }).execute()
        logger.info(f"Linked {source}:{external_id} to person {person_id}")

identity_service = IdentityResolutionService()
