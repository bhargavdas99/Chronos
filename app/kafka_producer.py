import json
import logging
import os
from typing import Optional
from aiokafka import AIOKafkaProducer

logger = logging.getLogger("chronos.kafka")

# Global singleton producer
producer: Optional[AIOKafkaProducer] = None

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
LEDGER_TOPIC = "ledger.transactions"


async def init_kafka() -> None:
    """Initializes and starts the singleton Kafka producer."""
    global producer
    try:
        producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
        )
        await producer.start()
        logger.info(f"Connected to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
    except Exception as e:
        logger.error(f"Failed to initialize Kafka producer: {e}")
        producer = None


async def close_kafka() -> None:
    """Gracefully shuts down the Kafka producer."""
    global producer
    if producer:
        await producer.stop()
        logger.info("Kafka producer stopped successfully.")


async def send_transaction_event(
    account_id: str,
    user_id: str,
    amount: float,
    entry_type: str,
    reference_id: Optional[str] = None,
) -> None:
    """
    Publishes a transaction audit event to Kafka asynchronously.
    Fails safely without raising exceptions to protect the primary DB transaction response.
    """
    global producer
    if not producer:
        logger.warning("Kafka producer not initialized. Skipping event emission.")
        return

    event_payload = {
        "event_type": "TRANSACTION_COMPLETED",
        "account_id": str(account_id),
        "user_id": user_id,
        "amount": float(amount),
        "entry_type": entry_type,
        "reference_id": str(reference_id) if reference_id else None,
    }

    try:
        # Use account_id as partition key so all events for the same account arrive in order
        await producer.send_and_wait(
            topic=LEDGER_TOPIC,
            key=str(account_id),
            value=event_payload,
        )
    except Exception as e:
        logger.error(f"Failed to publish Kafka event for account {account_id}: {e}")
