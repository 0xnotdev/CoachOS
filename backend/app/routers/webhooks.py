from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Path
from app.integrations.stripe_adapter import stripe_adapter
from app.services.state_engine import state_engine
from app.services.feature_store import feature_store_service
from app.services.signal_engine import signal_engine
from app.services.prediction_engine import prediction_engine
from app.services.decision_engine import decision_engine
from app.services.supabase_client import supabase_service
from uuid import UUID
import asyncio
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

async def execute_event_pipeline(canonical_event: dict, coach_id: str):
    """
    Executes the 10-layer data and prediction pipeline for a normalized event.
    Optimized to run independent stages concurrently to minimize roundtrip latency.
    """
    entity_id = canonical_event.get("entity_id")
    event_type = canonical_event.get("event_type")
    
    try:
        logger.info(f"Starting optimized parallel pipeline for entity {entity_id} under Coach {coach_id}")
        
        # Parallel Step 1: Update entity state and clear stale signals concurrently
        await asyncio.gather(
            state_engine.process_canonical_event(canonical_event),
            signal_engine.resolve_signals_for_event(entity_id, event_type)
        )
        
        # Step 2: Update Feature Store with latest averages (blocking checkpoint for signals/predictions)
        await feature_store_service.update_features(entity_id, canonical_event)
        
        # Parallel Step 3: Run signal evaluation rules and calculate churn models concurrently
        await asyncio.gather(
            signal_engine.evaluate_signals(entity_id, coach_id),
            prediction_engine.compute_predictions(entity_id)
        )
        
        # Step 4: Run decision logic to populate the Action Graph based on new signals/predictions
        await decision_engine.evaluate_decisions(entity_id, coach_id)
        
        logger.info(f"Successfully completed event pipeline execution for entity {entity_id}")
        
    except Exception as e:
        logger.error(f"CRITICAL: Event pipeline failed for entity {entity_id} under Coach {coach_id}: {e}", exc_info=True)

@router.post("/stripe/{webhook_token}")
async def stripe_webhook(
    request: Request, 
    background_tasks: BackgroundTasks,
    webhook_token: UUID = Path(..., description="The unique, unguessable webhook endpoint token registered for a coach")
):
    db = supabase_service.get_client()
    
    endpoint_res = await asyncio.to_thread(
        lambda: db.table("webhook_endpoints")
        .select("coach_id")
        .eq("webhook_token", str(webhook_token))
        .execute()
    )
    
    if not endpoint_res.data:
        logger.warning(f"Unauthorized or invalid webhook token received: {webhook_token}")
        raise HTTPException(status_code=401, detail="Invalid webhook endpoint token")
        
    coach_id = endpoint_res.data[0]["coach_id"]
    
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing signature header")

    try:
        canonical_event = await stripe_adapter.handle_webhook(payload, sig_header, str(coach_id))
        
        if canonical_event:
            background_tasks.add_task(execute_event_pipeline, canonical_event, str(coach_id))
            logger.info(f"Stripe event queued for Coach {coach_id}: {canonical_event.get('event_type')}")
            
    except Exception as e:
        logger.error(f"Stripe webhook processing failed for Coach {coach_id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
        
    return {"status": "success"}
