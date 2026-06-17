from fastapi import APIRouter, Request, HTTPException, Path
from app.integrations.stripe_adapter import stripe_adapter
from app.services.state_engine import state_engine
from app.services.feature_store import feature_store_service
from app.services.signal_engine import signal_engine
from app.services.prediction_engine import prediction_engine
from app.services.decision_engine import decision_engine
from app.services.supabase_client import supabase_service
from app.services.task_queue import task_queue, register_task
from app.config import settings
from app.utils.security import security_helper
from uuid import UUID
import asyncio
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

async def execute_event_pipeline(canonical_event: dict, coach_id: str):
    """
    Executes the 10-layer data and prediction pipeline for a normalized event.
    """
    entity_id = canonical_event.get("entity_id")
    event_type = canonical_event.get("event_type")
    
    try:
        logger.info(f"Starting optimized parallel pipeline for entity {entity_id} under Coach {coach_id}")
        
        await asyncio.gather(
            state_engine.process_canonical_event(canonical_event),
            signal_engine.resolve_signals_for_event(entity_id, event_type)
        )
        
        await feature_store_service.update_features(entity_id, canonical_event)
        
        await asyncio.gather(
            signal_engine.evaluate_signals(entity_id, coach_id),
            prediction_engine.compute_predictions(entity_id)
        )
        
        await decision_engine.evaluate_decisions(entity_id, coach_id)
        
        logger.info(f"Successfully completed event pipeline execution for entity {entity_id}")
        
    except Exception as e:
        logger.error(f"CRITICAL: Event pipeline failed for entity {entity_id} under Coach {coach_id}: {e}", exc_info=True)

@register_task("execute_event_pipeline")
async def execute_event_pipeline_task(payload: dict, coach_id: str):
    """
    Durable task queue worker adapter for executing event pipelines.
    """
    await execute_event_pipeline(payload, coach_id)

@router.post("/stripe/{webhook_token}")
async def stripe_webhook(
    request: Request, 
    webhook_token: UUID = Path(..., description="The unique, unguessable webhook endpoint token registered for a coach")
):
    db = supabase_service.get_client()
    
    # Resolve coach_id and the custom webhook secret for this coach integration endpoint
    endpoint_res = await asyncio.to_thread(
        lambda: db.table("webhook_endpoints")
        .select("coach_id, stripe_webhook_secret")
        .eq("webhook_token", str(webhook_token))
        .execute()
    )
    
    if not endpoint_res.data:
        logger.warning(f"Unauthorized webhook token: {webhook_token}")
        raise HTTPException(status_code=401, detail="Invalid webhook endpoint token")
        
    record = endpoint_res.data[0]
    coach_id = record["coach_id"]
    
    # Securely decrypt the webhook secret before constructing the verification event
    encrypted_secret = record.get("stripe_webhook_secret")
    if encrypted_secret:
        webhook_secret = security_helper.decrypt(encrypted_secret)
    else:
        webhook_secret = settings.STRIPE_WEBHOOK_SECRET
    
    if not webhook_secret:
        logger.error("No Stripe webhook secret configured on webhook endpoint or environment variables.")
        raise HTTPException(status_code=500, detail="Stripe webhook validation secret not configured.")
    
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing signature header")

    try:
        canonical_event = await stripe_adapter.handle_webhook(payload, sig_header, str(coach_id), webhook_secret)
        
        if canonical_event:
            # Enqueue task in SQLite queue using canonical event UUID as task_id (guarantees idempotency)
            task_id = canonical_event.get("id")
            await task_queue.enqueue(
                task_id=task_id,
                task_name="execute_event_pipeline",
                payload=canonical_event,
                coach_id=str(coach_id)
            )
            logger.info(f"Stripe event queued in durable task queue for Coach {coach_id}: {canonical_event.get('event_type')}")
            
    except Exception as e:
        logger.error(f"Stripe webhook processing failed for Coach {coach_id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
        
    return {"status": "success"}
