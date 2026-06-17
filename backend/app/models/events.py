from enum import Enum
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime
from uuid import UUID, uuid4

class EntityType(str, Enum):
    COACH = "coach"
    CLIENT = "client"
    LEAD = "lead"
    PROGRAM = "program"
    SUBSCRIPTION = "subscription"

class EventDomain(str, Enum):
    REVENUE = "revenue"
    ENGAGEMENT = "engagement"
    COMMUNICATION = "communication"
    ONBOARDING = "onboarding"
    COMPLIANCE = "compliance"
    PROGRAM = "program"
    SCHEDULING = "scheduling"
    RETENTION = "retention"
    SYSTEM = "system"

class IntegrationSource(str, Enum):
    STRIPE = "stripe"
    GOOGLE_SHEETS = "google_sheets"
    TYPEFORM = "typeform"
    WHATSAPP = "whatsapp"
    CALENDLY = "calendly"
    TRAINERIZE = "trainerize"
    EVERFIT = "everfit"
    NOTION = "notion"
    SYSTEM = "system"

class EventMetadata(BaseModel):
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    dedup_key: Optional[str] = None
    original_event_id: Optional[str] = None
    version: str = "1.0"

class CanonicalEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    coach_id: UUID
    entity_type: EntityType
    entity_id: UUID
    event_domain: EventDomain
    event_type: str  # e.g., "payment.succeeded", "checkin.submitted"
    source: IntegrationSource
    occurred_at: datetime
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    payload: Dict[str, Any]
    metadata: EventMetadata = Field(default_factory=EventMetadata)
