import asyncio
import json
import logging
import os
import signal
import sys
import aio_pika

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("chronos.worker")

RABBITMQ_USER = os.getenv("RABBITMQ_DEFAULT_USER", "chronos")
RABBITMQ_PASS = os.getenv("RABBITMQ_DEFAULT_PASS", "chronos123")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_URL = f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}:5672/"

QUEUE_NAME = "receipt_generation_queue"


async def process_task(message: aio_pika.IncomingMessage) -> None:
    """
    Processes a single message from RabbitMQ with explicit acknowledgment semantics.
    """
    # Context manager automatically handles ack/nack:
    # - If block finishes successfully -> sends basic.ack
    # - If an exception is raised -> sends basic.nack (and requeues message)
    async with message.process(requeue=True):
        payload = json.loads(message.body.decode("utf-8"))
        logger.info(
            f"Received Task [{payload.get('task_type')}]: "
            f"Entry ID={payload.get('entry_id')}, User={payload.get('user_id')}, "
            f"Amount={payload.get('amount')}"
        )

        # Simulate heavy background operation (e.g., PDF generation / S3 upload / Webhook dispatch)
        await asyncio.sleep(1.5)

        logger.info(
            f"Successfully generated receipt for Entry ID: {payload.get('entry_id')}"
        )


async def main() -> None:
    logger.info("Starting Chronos Background Task Worker...")

    # Establish robust connection to RabbitMQ
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()

    # Fair dispatch: Prefetch = 1 ensures worker only takes 1 task at a time,
    # preventing worker overload when multiple consumers are active.
    await channel.set_qos(prefetch_count=1)

    queue = await channel.declare_queue(QUEUE_NAME, durable=True)
    logger.info(f"Worker connected. Listening on queue: '{QUEUE_NAME}'...")

    # Start consuming messages
    await queue.consume(process_task)

    # Keep worker running until interrupt signal is received
    stop_event = asyncio.Event()

    def handle_signal():
        logger.info("Shutdown signal received. Stopping worker...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    await stop_event.wait()

    # Clean shutdown
    await channel.close()
    await connection.close()
    logger.info("Worker shut down cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker terminated.")
