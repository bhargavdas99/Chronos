import os
from typing import Optional
from fastapi import FastAPI, HTTPException, Header, status
from contextlib import asynccontextmanager

from app.db import init_db, close_db, get_pool
from app.idempotency import (
    init_redis,
    close_redis,
    handle_idempotency,
    save_idempotency_result,
    release_idempotency_lock,
)
from app.ledger import process_transaction
from app.schemas import CreateAccountRequest, TransactionRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    await init_db()
    await init_redis(redis_url)
    yield
    await close_redis()
    await close_db()


app = FastAPI(title="Chronos Financial Ledger Engine", lifespan=lifespan)


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
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(e)
        )

    # 3. Primary thread executes the DB transaction
    try:
        res = await process_transaction(
            pool=get_pool(),
            user_id=request.user_id,
            amount=request.amount,
            entry_type=request.entry_type,
            reference_id=request.reference_id,
        )
        await save_idempotency_result(idempotency_key, res)
        return res
    except Exception as e:
        # Release lock so future requests with this key aren't stuck if DB fails
        await release_idempotency_lock(idempotency_key)
        if isinstance(e, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Transaction Error: {str(e)}",
        )


# Processing of Non-idempotent path [we separated this from idempotent path above.]
async def _process_and_handle_errors(request: TransactionRequest):
    try:
        return await process_transaction(
            pool=get_pool(),
            user_id=request.user_id,
            amount=request.amount,
            entry_type=request.entry_type,
            reference_id=request.reference_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Transaction Error: {str(e)}",
        )