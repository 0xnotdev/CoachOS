import asyncio
from uuid import UUID
from app.services.supabase_client import supabase_service
import logging

logger = logging.getLogger(__name__)

class IdentityResolutionService:
    def __init__(self):
        self.db = None

    def _get_db(self):
        if not self.db:
            self.db = supabase_service.get_client()
        return self.db

    async def resolve_identity(self, source: str, external_id: str) -> UUID | None:
        """
        Resolves a source-specific ID (e.g., Stripe cus_123) to a global Person UUID.
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

    async def get_or_create_person(self, email: str, name: str) -> UUID:
        """
        Retrieves a Person UUID by email. If not found, attempts to insert a new Person.
        Normalizes email strings by trimming whitespace and lowercasing to prevent case-sensitive duplication.
        """
        normalized_email = email.strip().lower()
        try:
            return await asyncio.to_thread(self._get_or_create_person_sync, normalized_email, name)
        except Exception as e:
            logger.error(f"Error getting/creating person for email {normalized_email}: {e}")
            # Fallback query in case of race condition
            try:
                return await asyncio.to_thread(self._find_person_by_email_sync, normalized_email)
            except Exception as fe:
                logger.critical(f"Critical identity resolution failure for {normalized_email}: {fe}")
                raise fe

    def _find_person_by_email_sync(self, email: str) -> UUID:
        db = self._get_db()
        res = db.table("persons").select("id").eq("email", email).execute()
        if res.data:
            return UUID(res.data[0]["id"])
        raise ValueError(f"Person not found for email {email}")

    def _get_or_create_person_sync(self, email: str, name: str) -> UUID:
        db = self._get_db()
        
        # 1. Primary check
        res = db.table("persons").select("id").eq("email", email).execute()
        if res.data:
            return UUID(res.data[0]["id"])
            
        # 2. Insert attempt
        try:
            insert_res = db.table("persons").insert({"name": name, "email": email}).execute()
            return UUID(insert_res.data[0]["id"])
        except Exception as e:
            # If database raised unique key violation due to a concurrent race condition,
            # query the database again to retrieve the concurrently inserted row.
            logger.info(f"Concurrent insert detected for email {email}, performing fallback query.")
            return self._find_person_by_email_sync(email)

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
        # Safe link via ON CONFLICT DO NOTHING
        db.table('identities').upsert({
            "person_id": str(person_id),
            "source": source,
            "external_id": external_id
        }, on_conflict="source,external_id").execute()
        logger.info(f"Linked {source}:{external_id} to person {person_id}")

# Global singleton
identity_service = IdentityResolutionService()
