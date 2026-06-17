import contextvars
import logging
import structlog
import sys
from typing import Any, Dict

# Context variables to hold transaction metadata across async task contexts
request_id_ctx = contextvars.ContextVar("request_id", default="")
coach_id_ctx = contextvars.ContextVar("coach_id", default="")

def add_context_info(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Processor to inject contextvars (request_id, coach_id) into structured logs.
    """
    req_id = request_id_ctx.get()
    if req_id:
        event_dict["request_id"] = req_id
        
    coach_id = coach_id_ctx.get()
    if coach_id:
        event_dict["coach_id"] = coach_id
        
    return event_dict

def setup_logging():
    """
    Configures structlog to format logs in JSON format for production environment metrics.
    """
    # Standard library configuration to pipe through structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            add_context_info,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

class LogContext:
    """
    Context manager to bind/unbind coach_id and request_id block-wide.
    """
    def __init__(self, request_id: str = None, coach_id: str = None):
        self.request_id = request_id
        self.coach_id = coach_id
        self.tokens = []

    def __enter__(self):
        if self.request_id is not None:
            self.tokens.append(request_id_ctx.set(self.request_id))
        if self.coach_id is not None:
            self.tokens.append(coach_id_ctx.set(self.coach_id))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Reset context variables in reverse order of setting
        for token in reversed(self.tokens):
            if token.var is request_id_ctx:
                request_id_ctx.reset(token)
            elif token.var is coach_id_ctx:
                coach_id_ctx.reset(token)
