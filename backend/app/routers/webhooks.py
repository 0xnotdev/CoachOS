from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Path
from app.integrations.stripe_adapter import stripe_adapter
from app.services.state_engine import state_engine
from app.services.feature_store import feature_store_service
from app.services.signal_engine import signal_engine
from app.services.prediction_engine import prediction_engine
from app.services.decision_engine import decision_engine
from uuid import UUID
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

async def execute_event_pipeline(canonical_event: dict, coach_id: str):
    """
    Executes the 10-layer data and prediction pipeline for a normalized event under a specific coach context.
    """
    entity_id = canonical_event.get("entity_id")
    
    try:
        logger.info(f"Starting pipeline execution for entity {entity_id} under Coach {coach_id}")
        
        # Layer 4 & 5: State Engine & Temporal snapshots
        await state_engine.process_canonical_event(canonical_event)
        
        # Resolve any stale active signals first based on recovery events
        await signal_engine.resolve_signals_for_event(entity_id, canonical_event.get("event_type"))
        
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
        logger.error(f"CRITICAL: Event pipeline failed for entity {entity_id} under Coach {coach_id}: {e}", exc_info=True)

@router.post("/stripe/{coach_id}")
async def stripe_webhook(
    request: Request, 
    background_tasks: BackgroundTasks,
    coach_id: UUID = Path(..., description="The unique UUID of the coach owning this Stripe Integration")
):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing signature header")

    try:
        # Ingest and normalize event mapped to the specific coach
        canonical_event = await stripe_adapter.handle_webhook(payload, sig_header, str(coach_id))
        
        if canonical_event:
            # Dispatch async execution background task scoped to this coach
            background_tasks.add_task(execute_event_pipeline, canonical_event, str(coach_id))
            logger.info(f"Stripe event queued for Coach {coach_id}: {canonical_event.get('event_type')}")
            
    except Exception as e:
        logger.error(f"Stripe webhook processing failed for Coach {coach_id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
        
    return {"status": "success"}
