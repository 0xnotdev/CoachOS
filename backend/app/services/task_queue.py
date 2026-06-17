import sqlite3
import json
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# Registry of task handlers
TASK_REGISTRY: Dict[str, Callable[..., Coroutine]] = {}

def register_task(name: str):
    def decorator(func: Callable[..., Coroutine]):
        TASK_REGISTRY[name] = func
        return func
    return decorator

class SQLiteTaskQueue:
    def __init__(self, db_path: str = "tasks.db"):
        self.db_path = db_path
        self._init_db()
        self.worker_task = None
        self.running = False

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                task_name TEXT NOT NULL,
                payload TEXT NOT NULL,
                coach_id TEXT,
                status TEXT NOT NULL, -- pending, processing, completed, failed
                retry_count INTEGER DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL,
                run_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    async def enqueue(self, task_id: str, task_name: str, payload: dict, coach_id: str = None) -> bool:
        """
        Enqueues a task. Returns True if successfully enqueued,
        or False if it's a duplicate (idempotency guard).
        """
        now_str = datetime.now(timezone.utc).isoformat()
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tasks (id, task_name, payload, coach_id, status, retry_count, created_at, run_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (task_id, task_name, json.dumps(payload), coach_id, "pending", 0, now_str, now_str)
            )
            conn.commit()
            conn.close()
            logger.info(f"Task {task_id} ({task_name}) successfully enqueued.")
            return True
        except sqlite3.IntegrityError:
            logger.info(f"Duplicate task {task_id} ignored (idempotency guard).")
            return False
        except Exception as e:
            logger.error(f"Failed to enqueue task {task_id}: {e}")
            return False

    async def start_worker(self):
        self.running = True
        self.worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Durable SQLite Task Queue worker started.")

    async def stop_worker(self):
        self.running = False
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Durable SQLite Task Queue worker stopped.")

    async def _worker_loop(self):
        while self.running:
            try:
                await self._process_pending_tasks()
            except Exception as e:
                logger.error(f"Error in task queue worker loop: {e}")
            await asyncio.sleep(2) # Poll every 2 seconds

    async def _process_pending_tasks(self):
        db_path = self.db_path
        now_str = datetime.now(timezone.utc).isoformat()
        
        # 1. Fetch pending tasks ready to run
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, task_name, payload, coach_id, retry_count FROM tasks WHERE status = 'pending' AND run_at <= ?",
            (now_str,)
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return

        for task_id, task_name, payload_str, coach_id, retry_count in rows:
            # Mark task as processing
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE tasks SET status = 'processing' WHERE id = ?", (task_id,))
            conn.commit()
            conn.close()

            handler = TASK_REGISTRY.get(task_name)
            if not handler:
                err_msg = f"No handler registered for task: {task_name}"
                logger.error(err_msg)
                self._handle_failure(task_id, err_msg, retry_count)
                continue

            try:
                payload = json.loads(payload_str)
                # Run handler
                if coach_id:
                    await handler(payload, coach_id)
                else:
                    await handler(payload)
                
                # Mark as completed
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("UPDATE tasks SET status = 'completed' WHERE id = ?", (task_id,))
                conn.commit()
                conn.close()
                logger.info(f"Task {task_id} completed successfully.")

            except Exception as e:
                err_msg = str(e)
                logger.error(f"Error executing task {task_id}: {err_msg}")
                self._handle_failure(task_id, err_msg, retry_count)

    def _handle_failure(self, task_id: str, error_message: str, current_retry: int):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if current_retry >= 3:
            # Move to dead-letter queue (status = failed)
            cursor.execute(
                "UPDATE tasks SET status = 'failed', last_error = ?, retry_count = ? WHERE id = ?",
                (error_message, current_retry + 1, task_id)
            )
            logger.error(f"Task {task_id} failed after maximum retries. Moved to Dead Letter Queue.")
        else:
            # Exponential backoff (2 ** retry_count minutes)
            backoff_minutes = 2 ** current_retry
            next_run = datetime.now(timezone.utc) + timedelta(minutes=backoff_minutes)
            cursor.execute(
                "UPDATE tasks SET status = 'pending', last_error = ?, retry_count = ?, run_at = ? WHERE id = ?",
                (error_message, current_retry + 1, next_run.isoformat(), task_id)
            )
            logger.info(f"Task {task_id} scheduled for retry at {next_run.isoformat()} (Backoff: {backoff_minutes}m).")
            
        conn.commit()
        conn.close()

task_queue = SQLiteTaskQueue()
