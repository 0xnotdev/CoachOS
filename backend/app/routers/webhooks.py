from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from app.integrations.stripe_adapter import stripe_adapter
from app.services.state_engine import state_engine
from app.services.feature_store import feature_store_service
from app.services.signal_engine import signal_engine
from app.services.prediction_engine import prediction_engine
from app.services.decision_engine import decision_engine
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

async def execute_event_pipeline(canonical_event: dict):
    """
    Executes the 10-layer data and prediction pipeline for a normalized event.
    """
    entity_id = canonical_event.get("entity_id")
    # For MVP, resolving a default coach_id or fetching from database
    # In a real system, the client table links entity_id to coach_id.
    coach_id = "00000000-0000-0000-0000-000000000000" # Placeholder coach uuid
    
    try:
        logger.info(f"Starting pipeline execution for entity {entity_id}")
        
        # Layer 4 & 5: State Engine & Temporal snapshots
        await state_engine.process_canonical_event(canonical_event)
        
        # Layer 6: Feature Store updates
        await feature_store_service.update_features(entity_id, canonical_event)
        
        # Layer 8: Signal Detection Engine
        await signal_engine.evaluate_signals(entity_id, coach_id)
        
        # Layer 7: Prediction Engine
        await prediction_engine.compute_predictions(entity_id)
        
        # Layer 9 & 10: Decision & Action Graph
        await decision_engine.evaluate_decisions(entity_id, coach_id)
        
        logger.info(f"Successfully completed event pipeline execution for entity {entity_id}")
        
    except Exception as e:
        logger.error(f"CRITICAL: Event pipeline failed for entity {entity_id}: {e}", exc_info=True)
        # In production, route to a Dead Letter Queue (DLQ) or push alert to monitoring system (e.g. Sentry)

@router.post("/stripe")
async def stripe_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing signature header")

    try:
        # Ingest and normalize event
        canonical_event = await stripe_adapter.handle_webhook(payload, sig_header)
        
        if canonical_event:
            # Dispatch async execution background task
            background_tasks.add_task(execute_event_pipeline, canonical_event)
            logger.info(f"Stripe event queued for pipeline processing: {canonical_event.get('event_type')}")
            
    except Exception as e:
        logger.error(f"Stripe webhook processing failed: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
        
    return {"status": "success"}
