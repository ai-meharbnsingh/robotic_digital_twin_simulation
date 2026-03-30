"""
Dead Letter Queue — failed order processing queue.

Uses RabbitMQ when available, falls back to in-memory queue.
Graceful degradation: if RabbitMQ is unreachable, DLQ operates
in-memory only (data lost on restart, but no crashes).
"""

import asyncio
import logging
import time
import uuid

logger = logging.getLogger(__name__)

MAX_DLQ_SIZE = 10_000


class DeadLetterQueue:
    """Failed order processing queue.

    Uses in-memory storage with optional RabbitMQ persistence.
    Always works — RabbitMQ just adds durability.
    """

    def __init__(self, rabbitmq_url: str = ""):
        """
        Args:
            rabbitmq_url: RabbitMQ connection URL. If empty or unreachable,
                          falls back to in-memory only.
        """
        self._rabbitmq_url = rabbitmq_url
        self._dead_letters: list[dict] = []
        self._rabbitmq_connected = False

        # Attempt RabbitMQ connection (non-blocking, graceful)
        if rabbitmq_url:
            self._try_connect_rabbitmq()

    def _try_connect_rabbitmq(self):
        """Try to connect to RabbitMQ. Non-fatal if unavailable."""
        try:
            import pika
            params = pika.URLParameters(self._rabbitmq_url)
            params.socket_timeout = 2
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.queue_declare(queue="wms_dlq", durable=True)
            connection.close()
            self._rabbitmq_connected = True
            logger.info("DLQ connected to RabbitMQ")
        except Exception as exc:
            self._rabbitmq_connected = False
            logger.warning("DLQ RabbitMQ unavailable (in-memory mode): %s", exc)

    def _publish_to_rabbitmq(self, entry: dict) -> None:
        """Synchronous RabbitMQ publish — called via asyncio.to_thread()."""
        import json
        import pika
        params = pika.URLParameters(self._rabbitmq_url)
        params.socket_timeout = 2
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.basic_publish(
            exchange="",
            routing_key="wms_dlq",
            body=json.dumps(entry),
            properties=pika.BasicProperties(delivery_mode=2),
        )
        connection.close()

    async def enqueue(self, order: dict, error: str) -> dict:
        """Push failed order to DLQ with error reason.

        Args:
            order: The order that failed processing.
            error: Human-readable error description.

        Returns:
            Dict with message_id and status.
        """
        message_id = str(uuid.uuid4())[:12]
        entry = {
            "message_id": message_id,
            "order": order,
            "error": error,
            "enqueued_at": time.time(),
            "retry_count": 0,
            "status": "dead",
        }
        # Evict oldest entries if at capacity
        while len(self._dead_letters) >= MAX_DLQ_SIZE:
            self._dead_letters.pop(0)

        self._dead_letters.append(entry)

        # Also push to RabbitMQ if connected (in a thread to avoid blocking)
        if self._rabbitmq_connected:
            try:
                await asyncio.to_thread(self._publish_to_rabbitmq, entry)
            except Exception as exc:
                logger.warning("DLQ RabbitMQ publish failed: %s", exc)
                self._rabbitmq_connected = False

        logger.info("DLQ enqueued message %s: %s", message_id, error)
        return {"message_id": message_id, "status": "enqueued"}

    async def list_dead_letters(self, limit: int = 100) -> list[dict]:
        """List failed orders in the DLQ.

        Args:
            limit: Max number of entries to return.

        Returns:
            List of DLQ entries, newest first.
        """
        return list(reversed(self._dead_letters[-limit:]))

    async def retry(self, message_id: str) -> dict:
        """Mark a dead letter for retry.

        Args:
            message_id: The DLQ message ID to retry.

        Returns:
            Dict with retry status.

        Raises:
            KeyError: If message_id not found.
        """
        for entry in self._dead_letters:
            if entry["message_id"] == message_id:
                entry["retry_count"] += 1
                entry["status"] = "retrying"
                entry["last_retry_at"] = time.time()
                logger.info("DLQ retry message %s (attempt %d)", message_id, entry["retry_count"])
                return {
                    "message_id": message_id,
                    "status": "retrying",
                    "retry_count": entry["retry_count"],
                    "order": entry["order"],
                }
        raise KeyError(f"DLQ message not found: {message_id}")

    def get_status(self) -> dict:
        """Return DLQ status summary."""
        return {
            "total": len(self._dead_letters),
            "dead": sum(1 for e in self._dead_letters if e["status"] == "dead"),
            "retrying": sum(1 for e in self._dead_letters if e["status"] == "retrying"),
            "rabbitmq_connected": self._rabbitmq_connected,
        }
