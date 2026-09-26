from fastapi import FastAPI, HTTPException, status
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field
from decimal import Decimal
import uuid

from app.db import init_db, close_db, get_pool
from app.ledger import process_transaction

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()

app = FastAPI(title="Chronos Financial Ledger Engine", lifespan=lifespan)

class CreateAccountRequest(BaseModel):
    user_id: str
    initial_balance: Decimal = Field(ge=0, default=Decimal('0.0000'))

class TransactionRequest(BaseModel):
    user_id: str
    amount: Decimal = Field(gt=0)
    entry_type: str
    reference_id: uuid.UUID | None = None

@app.post("/accounts", status_code=status.HTTP_201_CREATED)
async def create_account(req: CreateAccountRequest):
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO accounts (user_id, balance) 
                VALUES ($1, $2) 
                RETURNING account_id, user_id, balance
                """,
                req.user_id, req.initial_balance
            )
            return {
                "account_id": str(row["account_id"]),
                "user_id": row["user_id"],
                "balance": float(row["balance"])
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

@app.post("/ledger/transaction")
async def execute_transaction(req: TransactionRequest):
    pool = get_pool()
    try:
        res = await process_transaction(
            pool=pool,
            user_id=req.user_id,
            amount=req.amount,
            entry_type=req.entry_type,
            reference_id=req.reference_id
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Transaction Error: " + str(e))