import asyncio
import logging
import json
import uuid
from typing import Dict, Any
from app.services.task_queue import register_task, task_queue
from app.services.supabase_client import supabase_service

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self):
        self.db = None

    def _get_db(self):
        if not self.db:
            self.db = supabase_service.get_client()
        return self.db

    async def enqueue_notification(self, coach_id: str, title: str, body: str, channel: str = "email"):
        """
        Enqueues a notification task to be dispatched asynchronously by the task queue.
        """
        task_id = str(uuid.uuid4())
        payload = {
            "title": title,
            "body": body,
            "channel": channel
        }
        await task_queue.enqueue(
            task_id=task_id,
            task_name="send_notification",
            payload=payload,
            coach_id=coach_id
        )
        logger.info(f"Enqueued notification task {task_id} for Coach {coach_id} via {channel}")

    async def dispatch_notification(self, payload: Dict[str, Any], coach_id: str):
        """
        Dispatches notification payload using the configured channel (email, whatsapp, push).
        Simulates channel delivery with structured outputs.
        """
        db = self._get_db()
        channel = payload.get("channel", "email")
        title = payload.get("title", "")
        body = payload.get("body", "")

        # 1. Fetch coach identity details (e.g., email or phone)
        coach_res = await asyncio.to_thread(
            lambda: db.table("coaches")
            .select("*, persons(name, email, phone)")
            .eq("id", coach_id)
            .execute()
        )
        
        coach_name = "Coach"
        coach_email = "coach@coachos.internal"
        coach_phone = "+15555555555"

        if coach_res.data:
            coach_data = coach_res.data[0]
            person_data = coach_data.get("persons", {})
            if person_data:
                coach_name = person_data.get("name", coach_name)
                coach_email = person_data.get("email", coach_email)
                coach_phone = person_data.get("phone", coach_phone)

        # 2. Dispatch simulated notification based on selected channel
        if channel == "email":
            logger.info(
                f"[NOTIFICATION DISPATCHER - EMAIL] Sending to {coach_name} <{coach_email}>\n"
                f"Subject: {title}\n"
                f"Body: {body}\n"
                f"Status: Delivered successfully."
            )
        elif channel == "whatsapp":
            logger.info(
                f"[NOTIFICATION DISPATCHER - WHATSAPP] Sending to phone {coach_phone}\n"
                f"Message: {title} - {body}\n"
                f"Status: Sent."
            )
        elif channel == "push":
            logger.info(
                f"[NOTIFICATION DISPATCHER - PUSH] Dispatching push alert to registered devices for Coach {coach_id}\n"
                f"Title: {title}\n"
                f"Body: {body}\n"
                f"Status: Broadcasted."
            )
        else:
            raise ValueError(f"Unknown notification dispatch channel: {channel}")

# Global singleton
notification_service = NotificationService()

# Register the task handler with the queue registry
@register_task("send_notification")
async def send_notification_task_handler(payload: Dict[str, Any], coach_id: str):
    await notification_service.dispatch_notification(payload, coach_id)
