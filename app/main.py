from fastapi import FastAPI, HTTPException, status
from contextlib import asynccontextmanager

from app.db import init_db, close_db, get_pool
from app.ledger import process_transaction
from app.schemas import CreateAccountRequest, TransactionRequest

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
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
                request.user_id, request.initial_balance
            )
            return {
                "account_id": str(row["account_id"]),
                "user_id": row["user_id"],
                "balance": float(row["balance"])
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

@app.post("/ledger/transaction")
async def execute_transaction(request: TransactionRequest):
    pool = get_pool()
    try:
        res = await process_transaction(
            pool=pool,
            user_id=request.user_id,
            amount=request.amount,
            entry_type=request.entry_type,
            reference_id=request.reference_id
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal Transaction Error: {str(e)}")