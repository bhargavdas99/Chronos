import asyncio
from typing import Optional
from fastapi import FastAPI, HTTPException, Header, status
from contextlib import asynccontextmanager

from app.core.db import init_db, close_db, get_pool
from app.core.idempotency import (
    init_redis,
    close_redis,
    handle_idempotency,
    save_idempotency_result,
    release_idempotency_lock,
)
from app.api.ledger import process_transaction
from app.api.schemas import CreateAccountRequest, TransactionRequest
from app.messaging.kafka_producer import init_kafka, close_kafka, send_transaction_event
from app.messaging.rabbitmq_producer import (
    init_rabbitmq,
    close_rabbitmq,
    publish_receipt_task,
)
from prometheus_fastapi_instrumentator import Instrumentator
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_url = settings.REDIS_URL
    await init_db()
    await init_redis(redis_url)
    await init_kafka()
    await init_rabbitmq()
    yield
    await close_rabbitmq()
    await close_kafka()
    await close_redis()
    await close_db()


app = FastAPI(title="Chronos Financial Ledger Engine", lifespan=lifespan)

# Initialize Prometheus instrumentator
Instrumentator().instrument(app).expose(
    app, endpoint="/metrics", include_in_schema=False
)


@app.post("/accounts", status_code=status.HTTP_201_CREATED)
async def create_account(request: CreateAccountRequest):
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO accounts (user_id, balance) 
                VALUES ($1, $2) 
                RETURNING account_id, user_id, balance
                """,
                request.user_id,
                request.initial_balance,
            )
            return {
                "account_id": str(row["account_id"]),
                "user_id": row["user_id"],
                "balance": float(row["balance"]),
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))


@app.post("/ledger/transaction")
async def execute_transaction(
    request: TransactionRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    # 1. Non-idempotent path (if no key passed)
    if not idempotency_key:
        return await _process_and_handle_errors(request)

    # 2. Idempotent path with Redis concurrency lock
    try:
        cached_result, is_primary = await handle_idempotency(idempotency_key)
        if cached_result:
            return cached_result
    except TimeoutError as e:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(e))

    # 3. Primary thread executes the DB transaction
    try:
        res = await process_transaction(
            pool=get_pool(),
            user_id=request.user_id,
            amount=request.amount,
            entry_type=request.entry_type,
            idempotency_key=idempotency_key,
            reference_id=request.reference_id,
        )

        # Save result for future idempotent callers
        await save_idempotency_result(idempotency_key, res)

        # Non-blocking event streaming to Kafka
        asyncio.create_task(
            send_transaction_event(
                account_id=res["account_id"],
                user_id=request.user_id,
                amount=request.amount,
                entry_type=request.entry_type,
                reference_id=request.reference_id,
            )
        )
        # Non-blocking background task to RabbitMQ
        asyncio.create_task(
            publish_receipt_task(
                account_id=res["account_id"],
                user_id=request.user_id,
                amount=request.amount,
                entry_type=request.entry_type,
                entry_id=res["entry_id"],
            )
        )

        return res
    except Exception as e:
        # Release lock so future requests with this key aren't stuck if DB fails
        await release_idempotency_lock(idempotency_key)
        if isinstance(e, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Transaction Error: {str(e)}",
        )


# Processing of Non-idempotent path [we separated this from idempotent path above.]
async def _process_and_handle_errors(request: TransactionRequest):
    try:
        res = await process_transaction(
            pool=get_pool(),
            user_id=request.user_id,
            amount=request.amount,
            entry_type=request.entry_type,
            reference_id=request.reference_id,
        )

        # Non-blocking event streaming to Kafka
        asyncio.create_task(
            send_transaction_event(
                account_id=res["account_id"],
                user_id=request.user_id,
                amount=request.amount,
                entry_type=request.entry_type,
                reference_id=request.reference_id,
            )
        )

        # Non-blocking background task to RabbitMQ
        asyncio.create_task(
            publish_receipt_task(
                account_id=res["account_id"],
                user_id=request.user_id,
                amount=request.amount,
                entry_type=request.entry_type,
                entry_id=res["entry_id"],
            )
        )

        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Transaction Error: {str(e)}",
        )
