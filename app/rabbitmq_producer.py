import json
import logging
import os
from typing import Optional
import aio_pika

logger = logging.getLogger("chronos.rabbitmq")

# Global singleton connection and channel
connection: Optional[aio_pika.RobustConnection] = None
channel: Optional[aio_pika.RobustChannel] = None

RABBITMQ_USER = os.getenv("RABBITMQ_DEFAULT_USER", "chronos")
RABBITMQ_PASS = os.getenv("RABBITMQ_DEFAULT_PASS", "chronos123")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_URL = f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}:5672/"

QUEUE_NAME = "receipt_generation_queue"


async def init_rabbitmq() -> None:
    """Initializes a robust connection and channel to RabbitMQ."""
    global connection, channel
    try:
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        channel = await connection.channel()

        # Declare queue as durable so messages survive broker restarts
        await channel.declare_queue(QUEUE_NAME, durable=True)
        logger.info(f"Connected to RabbitMQ at {RABBITMQ_HOST} (Queue: {QUEUE_NAME})")
    except Exception as e:
        logger.error(f"Failed to initialize RabbitMQ client: {e}")
        connection = None
        channel = None


async def close_rabbitmq() -> None:
    """Gracefully closes RabbitMQ channel and connection."""
    global connection, channel
    if channel and not channel.is_closed:
        await channel.close()
    if connection and not connection.is_closed:
        await connection.close()
        logger.info("RabbitMQ connection closed successfully.")


async def publish_receipt_task(
    account_id: str,
    user_id: str,
    amount: float,
    entry_type: str,
    entry_id: str,
) -> None:
    """
    Publishes a receipt generation task to RabbitMQ asynchronously.
    Fails safely without raising exceptions to protect the core DB transaction.
    """
    global channel
    if not channel:
        logger.warning("RabbitMQ channel not initialized. Skipping task dispatch.")
        return

    task_payload = {
        "task_type": "GENERATE_RECEIPT",
        "account_id": str(account_id),
        "user_id": user_id,
        "amount": float(amount),
        "entry_type": entry_type,
        "entry_id": str(entry_id),
    }

    try:
        message = aio_pika.Message(
            body=json.dumps(task_payload).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,  # Save message to disk on RabbitMQ broker
            content_type="application/json",
        )

        # Publish to default exchange targeting QUEUE_NAME
        await channel.default_exchange.publish(
            message,
            routing_key=QUEUE_NAME,
        )
    except Exception as e:
        logger.error(f"Failed to publish RabbitMQ task for entry {entry_id}: {e}")
